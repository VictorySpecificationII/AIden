"""AIden choosing their own models: browse, pull, trial (with model-steward's hands).

AIden decides; model-steward (tools/model-steward) does the pulling and config edits and
enforces the limits itself. This module:
- reads the steward's state: which model is active, previous and on trial per device;
- browses OpenVINO's catalog on Hugging Face for candidates that fit a device and the
  limits, best first, skipping models already tried;
- pulls a candidate and puts it on trial next to the active model, waiting until it is
  loaded and answering.
Scoring and switching build on this (see evaluate/scout below). Every step is recorded
as experience (kind "model"), which is also AIden's journal of model decisions.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter
from opentelemetry import metrics

import evals
import experience

STEWARD_URL = os.environ.get("STEWARD_URL", "http://model-steward:8770")
STEWARD_TOKEN = os.environ.get("STEWARD_TOKEN", "")
HF = "https://huggingface.co"
# Device -> the backend serving it
SERVERS = {"npu": ("ovms-npu", "http://ovms-npu:8001"), "gpu": ("ovms-gpu", "http://ovms-gpu:8002")}
CATALOG_SIZE = 40
LOAD_TIMEOUT_S = 30 * 60   # NPU compilation of a new model can take minutes
PULL_TIMEOUT_S = 3 * 3600

logger = logging.getLogger("aiden.models")
_state: Dict[str, Any] = {"at": 0.0, "value": None}
_state_lock = threading.Lock()


class StewardError(Exception):
    pass


def steward(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.request(method, f"{STEWARD_URL}{path}", json=body, timeout=60,
                                headers={"X-Steward-Token": STEWARD_TOKEN})
    data = response.json()
    if response.status_code != 200:
        raise StewardError(data.get("error", f"HTTP {response.status_code}"))
    return data


def state(max_age_s: float = 10) -> Optional[Dict[str, Any]]:
    """The steward's state (cached briefly); None when there is no steward."""
    if not STEWARD_TOKEN:
        return None
    with _state_lock:
        if _state["value"] is None or time.time() - _state["at"] > max_age_s:
            try:
                _state.update(value=steward("GET", "/state"), at=time.time())
            except (requests.RequestException, ValueError, StewardError) as exc:
                logger.warning("Could not read the model steward's state: %s", exc)
                return _state["value"]
        return _state["value"]


def active_model(backend: str) -> Optional[str]:
    """The model a backend should answer with: the steward's active one, if it manages it."""
    current = state()
    for device, (name, _) in SERVERS.items():
        if name == backend and current and device in current["devices"]:
            return current["devices"][device]["active"]
    return None


def journal(action: str, **fields):
    experience.record("model", {"action": action, **fields})
    logger.info("Models: %s %s", action, json.dumps(fields, default=str)[:300])


def tried() -> set:
    """Models AIden has already pulled or judged (so the same one isn't tried twice)."""
    seen = set()
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR)) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if path.endswith(".jsonl"):
            with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
                for line in f:
                    if '"kind": "model"' in line:
                        source = json.loads(line).get("source")
                        if source:
                            seen.add(source)
    return seen


def catalog(device: str) -> List[Dict[str, Any]]:
    """Candidates for a device within the steward's limits, most-used first."""
    current = state()
    if not current:
        return []
    limits = current["limits"]
    suffix = limits["devices"][device]
    listed = requests.get(f"{HF}/api/models", timeout=30, params={
        "author": limits["org"], "search": suffix, "sort": "downloads", "limit": CATALOG_SIZE}).json()
    have = {m["source"] for m in current["models"].values()} | tried()
    active_size = model_size(current, device)
    room = free_memory_gb() - limits.get("min_free_gb", 4)
    found = []
    for item in listed:
        source = item["id"]
        if not source.endswith(suffix) or source in have:
            continue
        info = requests.get(f"{HF}/api/models/{source}", params={"blobs": "true"}, timeout=30).json()
        licence = ((info.get("cardData") or {}).get("license") or "").lower()
        if licence not in limits["licences"] or info.get("pipeline_tag") not in (None, "text-generation"):
            continue
        size_gb = sum(f.get("size") or 0 for f in info.get("siblings", [])) / 1e9
        # Much smaller than the current model is unlikely to be better; too big won't load
        if (active_size and size_gb < 0.5 * active_size) or size_gb * 1.2 > room:
            continue
        found.append({"source": source, "size_gb": round(size_gb, 1), "licence": licence,
                      "downloads": item.get("downloads", 0)})
    return found


def model_size(current: Dict[str, Any], device: str) -> Optional[float]:
    """Size of the device's active model, from the steward or else Hugging Face."""
    active = current["models"].get(current["devices"].get(device, {}).get("active") or "", {})
    if active.get("size_gb"):
        return active["size_gb"]
    try:
        info = requests.get(f"{HF}/api/models/{active['source']}", params={"blobs": "true"}, timeout=30).json()
        return sum(f.get("size") or 0 for f in info.get("siblings", [])) / 1e9
    except (requests.RequestException, KeyError, ValueError):
        return None


def free_memory_gb() -> float:
    import re
    with open("/proc/meminfo") as f:
        fields = dict(re.findall(r"^(\w+):\s+(\d+) kB", f.read(), re.M))
    return int(fields["MemAvailable"]) / 1024 / 1024


def wait_until_answering(device: str, name: str, timeout_s: float = LOAD_TIMEOUT_S) -> bool:
    _, server = SERVERS[device]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if requests.get(f"{server}/v2/models/{name}/ready", timeout=5).status_code == 200:
                reply = requests.post(f"{server}/v3/chat/completions", timeout=120, json={
                    "model": name, "max_tokens": 5, "messages": [{"role": "user", "content": "Say OK."}]})
                if reply.status_code == 200:
                    return True
        except requests.RequestException:
            pass
        time.sleep(15)
    return False


def pull(source: str, device: str) -> str:
    job = steward("POST", "/pull", {"source": source, "device": device})
    journal("pull", source=source, device=device, size_gb=job["size_gb"])
    deadline = time.time() + PULL_TIMEOUT_S
    while time.time() < deadline:
        status = steward("GET", f"/jobs/{job['job']}")
        if status["state"] == "done":
            return job["name"]
        if status["state"] == "failed":
            raise StewardError(f"pull failed: {status.get('error', '')[-200:]}")
        time.sleep(20)
    raise StewardError("pull timed out")


def start_trial(source: str, device: str) -> str:
    """Pull a candidate, load it next to the active model and wait until it answers."""
    name = pull(source, device)
    steward("POST", "/trial", {"device": device, "name": name})
    journal("trial", source=source, device=device, name=name)
    if not wait_until_answering(device, name):
        steward("POST", "/end-trial", {"device": device})
        journal("trial_failed", source=source, device=device, name=name, reason="never answered")
        raise StewardError(f"{name} didn't load on the {device}")
    _state["at"] = 0  # re-read the steward's state next time
    return name


# --- Scoring ------------------------------------------------------------------------

MIN_TOKENS_PER_S = float(os.environ.get("AIDEN_MODEL_MIN_TPS", "5"))
ROUTING_SAMPLES = 40


# Known answers every candidate faces, so a model can't pass without being asked (in the
# user's world: their notes hold projects, clients, plans and decisions)
BENCHMARK = [(p, True) for p in [
    "What did I decide about MinIO for the AIden stack?", "Summarise my notes on the burn-in plan",
    "What are my client deliverables for next month?", "Remind me what we said about the Ceph upgrade",
    "What's in my Brazilian Portuguese notes about verb tenses?", "How did I set up Bitwarden secrets for Claude?",
    "What's the status of my HPC engineering project?", "Which decisions did I record about the NPU adaptation?",
    "What did I write about the Marina Ayia Napa pitch?", "List the open tasks in my LSDT HPC notes",
]] + [(p, False) for p in [
    "Explain how TCP slow start works", "What is the capital of France?", "Write a haiku about autumn",
    "How do I reverse a list in Python?", "What is the difference between RAID 5 and RAID 6?",
    "Translate 'good morning' into Spanish", "What does a TLB do in a CPU?", "How many days are in a leap year?",
    "Give me a recipe for pancakes", "What is Kubernetes used for?",
]]


def routing_questions(limit: int = ROUTING_SAMPLES) -> List[Dict[str, Any]]:
    """Prompts whose answer is known: the built-in benchmark plus turns the rules decided."""
    picked: Dict[bool, List[Dict[str, Any]]] = {True: [], False: []}
    for prompt, needs in BENCHMARK:
        picked[needs].append({"prompt": prompt, "needs_notes": needs})
    seen = {prompt for prompt, _ in BENCHMARK}
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR), reverse=True) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if not path.endswith(".jsonl"):
            continue
        with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                decision = record.get("decision") or {}
                prompt = record.get("prompt") or ""
                if record.get("kind") == "turn" and decision.get("decided_by") == "rule" and prompt not in seen:
                    seen.add(prompt)
                    picked[bool(decision.get("needs_notes"))].append({"prompt": prompt, "needs_notes": bool(decision["needs_notes"])})
    half = limit // 2
    return picked[True][:half] + picked[False][:limit - min(half, len(picked[True]))]


def routing_outcomes(model: str, questions: List[Dict[str, Any]], classify=None) -> List[bool]:
    """Per question: did the model route it right? (classify can stand in for a model.)"""
    from router import classify_with_npu
    classify = classify or (lambda prompt: classify_with_npu(prompt, model)[0])
    return [classify(q["prompt"]) == q["needs_notes"] for q in questions]


def accuracy(outcomes: List[bool]) -> Optional[float]:
    return round(sum(outcomes) / len(outcomes), 3) if outcomes else None


def speed(device: str, model: str) -> Optional[float]:
    _, server = SERVERS[device]
    start = time.time()
    try:
        response = requests.post(f"{server}/v3/chat/completions", timeout=180, json={
            "model": model, "max_tokens": 100, "temperature": 0,
            "messages": [{"role": "user", "content": "Explain in a short paragraph what an operating system does."}]})
        response.raise_for_status()
        tokens = response.json()["usage"]["completion_tokens"]
        return round(tokens / (time.time() - start), 1)
    except (requests.RequestException, KeyError, ValueError):
        return None


# The GPU answers: questions whose answers can be checked automatically, plus two that
# can't be known, where a well-calibrated model says its confidence is low
ANSWER_BENCHMARK = [
    ("What is 17 * 23? Reply with just the number.", [r"\b391\b"]),
    ("What is the capital of Australia?", [r"canberra"]),
    ("What is the chemical symbol for gold?", [r"\bAu\b"]),
    ("How many bytes are in a kibibyte?", [r"\b1024\b|1,024"]),
    ("What does this Python print? print(sorted([3, 1, 2])[-1])", [r"\b3\b"]),
    ("Which TCP port does SSH use by default?", [r"\b22\b"]),
    ("Reply with only the word ready, in lowercase.", [r"^\W*ready\W*$"]),
    ("Translate 'thank you' into Portuguese.", [r"obrigad"]),
    ("Which Linux command shows free disk space in human-readable form?", [r"df\s+-h"]),
    ("What is the time complexity of binary search?", [r"log"]),
    ("A train travels 120 km in 1.5 hours. What is its average speed in km/h?", [r"\b80\b"]),
    ("What is the process with PID 1 on most modern Linux distributions?", [r"systemd"]),
    ("What is 2 to the power of 10?", [r"\b1024\b|1,024"]),
    ("Which RAID level mirrors data across two disks?", [r"raid[\s-]?1\b"]),
    ("Name the three primary colours of light.", [r"red", r"green", r"blue"]),
    ("In which year did humans first land on the Moon?", [r"\b1969\b"]),
    ("Which HTTP status code means Not Found?", [r"\b404\b"]),
    ("What does ls -a show that plain ls hides?", [r"hidden|dot"]),
    ("Convert hexadecimal 0x1F to decimal.", [r"\b31\b"]),
    ("What is the boiling point of water at sea level in degrees Celsius?", [r"\b100\b"]),
]
UNKNOWABLE = ["What will the EUR/USD exchange rate be next Friday?", "What number am I thinking of right now?"]


def ask_answer(device: str, model: str, question: str) -> str:
    from router import backend_request, build_messages
    _, server = SERVERS[device]
    response = backend_request(f"{server}/v3", model, build_messages([{"role": "user", "content": question}], []),
                               False, {"max_tokens": 250, "temperature": 0}, [])
    return response.json()["choices"][0]["message"]["content"] or ""


def plain_reply(device: str, model: str, prompt: str, max_tokens: int) -> str:
    """A reply without AIden's system prompt: raw ability, as the public test sets expect."""
    from router import backend_request
    _, server = SERVERS[device]
    response = backend_request(f"{server}/v3", model, [{"role": "user", "content": prompt}], False,
                               {"max_tokens": max_tokens, "temperature": 0}, [])
    return response.json()["choices"][0]["message"]["content"] or ""


def answer_quality(device: str, model: str) -> Dict[str, Any]:
    """Share of checkable answers right, and how well the model follows AIden's confidence
    protocol (a confidence line on every answer, low when it can't know)."""
    import re
    from router import split_confidence
    right, with_confidence, honest, transcript, outcomes = 0, 0, 0, [], []
    for question, patterns in ANSWER_BENCHMARK:
        try:
            text, confidence = split_confidence(ask_answer(device, model, question))
        except Exception as exc:  # a failed answer counts as wrong
            text, confidence = f"[failed: {type(exc).__name__}]", None
        correct = checks_out(text, patterns)
        right += correct
        outcomes.append(correct)
        with_confidence += confidence is not None
        transcript.append({"q": question, "a": text[:300], "correct": correct})
    for question in UNKNOWABLE:
        try:
            text, confidence = split_confidence(ask_answer(device, model, question))
        except Exception:
            text, confidence = "", None
        honest += confidence == "low"
        transcript.append({"q": question, "a": text[:300], "confidence": confidence})
    total = len(ANSWER_BENCHMARK)
    return {"answers": round(right / total, 3), "confidence_lines": round(with_confidence / total, 3),
            "honest_when_unsure": round(honest / len(UNKNOWABLE), 3), "transcript": transcript, "outcomes": outcomes}


def checks_out(text: str, patterns: List[str]) -> bool:
    import re
    return all(re.search(p, text, re.I | re.M) for p in patterns)


def evaluate(device: str, model: str, questions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One model's scores for its device's job. quality is what decides: routing accuracy
    for the NPU (it classifies), answer quality for the GPU (it answers)."""
    import senses
    _, server = SERVERS[device]
    tools, tools_detail = senses.follows_tool_protocol(f"{server}/v3", model)
    result = {"model": model, "tools": tools, "tools_detail": tools_detail, "tokens_per_s": speed(device, model)}
    if device == "gpu":
        answers = answer_quality(device, model)
        checked = evals.checked_outcomes(lambda prompt, max_tokens: plain_reply(device, model, prompt, max_tokens),
                                         questions or {}) if isinstance(questions, dict) else {}
        outcomes = answers["outcomes"] + [o for name in sorted(checked) for o in checked[name]]
        # Right answers count most; following AIden's confidence protocol is part of the job
        quality = round(0.7 * accuracy(outcomes) + 0.15 * answers["confidence_lines"]
                        + 0.15 * answers["honest_when_unsure"], 3)
        result.update(quality=quality, answer_scores=answers, outcomes=outcomes,
                      checked={"benchmark": answers["answers"], **{n: accuracy(o) for n, o in checked.items()}})
    else:
        questions = questions if questions is not None else routing_questions()
        outcomes = routing_outcomes(model, questions)
        result.update(quality=accuracy(outcomes), routing_questions=len(questions), outcomes=outcomes,
                      baseline=trivial_baseline(questions))
    return result


# --- Is the measurement itself sound? ---------------------------------------------------

MIN_QUESTIONS = 20
BASELINE_MARGIN = 0.1       # must beat always-yes / always-no by this much
SIGNIFICANCE = 0.1          # one-sided p-value for "better", from per-question wins


def trivial_baseline(questions: List[Dict[str, Any]]) -> float:
    """The best a classifier that always says yes (or always no) would score."""
    if not questions:
        return 1.0
    yes = sum(q["needs_notes"] for q in questions) / len(questions)
    return round(max(yes, 1 - yes), 3)


def measurement_problems(device: str, questions: List[Dict[str, Any]]) -> List[str]:
    """Canaries: run the scoring on stand-ins whose result is known. If they come out wrong,
    the measurement is broken and nothing may be decided on it."""
    problems = []
    if device == "gpu":
        empty = sum(checks_out("I don't know.", patterns) for _, patterns in ANSWER_BENCHMARK)
        if empty:
            problems.append(f"an empty answer passes {empty} answer checks")
        if len(ANSWER_BENCHMARK) < MIN_QUESTIONS:
            problems.append(f"only {len(ANSWER_BENCHMARK)} answer questions")
        if isinstance(questions, dict):
            for name, rows in questions.items():
                if len(rows) < MIN_QUESTIONS:
                    problems.append(f"only {len(rows)} {name} questions")
            # Canaries: the true answers must pass the checks, and "I don't know" must fail them
            truth = {"gsm8k": lambda r: f"Answer: {evals.gsm8k_truth(r):g}", "mmlu_pro": lambda r: r["answer"]}
            for name, rows in questions.items():
                if evals.checked_outcomes(lambda p, t, r=iter(rows): truth[name](next(r)), {name: rows})[name].count(False):
                    problems.append(f"the true {name} answers don't all pass the checks")
                if any(evals.checked_outcomes(lambda p, t: "I don't know.", {name: rows})[name]):
                    problems.append(f"'I don't know' passes {name} checks")
    else:
        if len(questions) < MIN_QUESTIONS:
            problems.append(f"only {len(questions)} routing questions (need {MIN_QUESTIONS})")
        perfect = {q["prompt"]: q["needs_notes"] for q in questions}
        if questions and accuracy(routing_outcomes("", questions, perfect.get)) != 1.0:
            problems.append("a perfect classifier doesn't score 100%")
        if trivial_baseline(questions) > 0.7:
            problems.append(f"the questions are unbalanced (always-yes/no scores {trivial_baseline(questions)})")
    return problems


def p_better(candidate: List[bool], active: List[bool]) -> float:
    """One-sided sign test on the questions where the two disagree: the chance the
    candidate wins at least this often if both were equally good."""
    from math import comb
    wins = sum(c and not a for c, a in zip(candidate, active))
    losses = sum(a and not c for c, a in zip(candidate, active))
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(comb(n, k) for k in range(wins, n + 1)) / 2 ** n


def claude_opinion(device: str, candidate: Dict[str, Any], active: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The mentor's second opinion on the two models' benchmark answers (generic questions,
    never the user's notes). Recorded, not decisive; None when the mentor isn't available."""
    import mentor
    if device != "gpu" or not mentor.MENTOR_TOKEN:
        return None
    pairs = []
    for a, b in zip(candidate["answer_scores"]["transcript"], active["answer_scores"]["transcript"]):
        pairs.append(f"Q: {a['q']}\nA: {a['a']}\nB: {b['a']}")
    question = ("Two local language models, A and B, answered the same questions. Grade each model "
                "from 1 to 10 for correctness, clarity and honesty about uncertainty. Reply with only "
                'JSON: {"A": <score>, "B": <score>, "why": "<one sentence>"}\n\n' + "\n\n".join(pairs))
    try:
        reply = mentor.ask_mentor(question, "", [])["answer"]
        start, end = reply.find("{"), reply.rfind("}")
        grades = json.loads(reply[start:end + 1])
        return {"candidate": grades.get("A"), "active": grades.get("B"), "why": grades.get("why")}
    except Exception as exc:
        logger.info("No second opinion from the mentor: %s", exc)
        return None


def better(candidate: Dict[str, Any], active: Dict[str, Any]) -> Tuple[bool, str]:
    """Switch only to a candidate that is at least as good everywhere and better somewhere,
    by more than chance, and clearly better than a trivial classifier."""
    if candidate["quality"] is None:
        return False, "couldn't measure its quality"
    if len(candidate.get("outcomes") or []) < MIN_QUESTIONS:
        return False, f"measured on too few questions ({len(candidate.get('outcomes') or [])})"
    if "baseline" in candidate and candidate["quality"] < candidate["baseline"] + BASELINE_MARGIN:
        return False, f"barely beats always-yes/no ({candidate['quality']} vs {candidate['baseline']})"
    if candidate["tokens_per_s"] is None or candidate["tokens_per_s"] < MIN_TOKENS_PER_S:
        return False, f"too slow ({candidate['tokens_per_s']} tok/s, need {MIN_TOKENS_PER_S:.0f})"
    if (candidate["quality"] or 0) < (active["quality"] or 0):
        return False, f"scores worse ({candidate['quality']} vs {active['quality']})"
    if active["tools"] and not candidate["tools"]:
        return False, "can't use tools, the active model can"
    gains = []
    if candidate["tools"] and not active["tools"]:
        gains.append("can use tools")
    if (candidate["quality"] or 0) > (active["quality"] or 0):
        p = p_better(candidate.get("outcomes") or [], active.get("outcomes") or [])
        if p <= SIGNIFICANCE:
            gains.append(f"scores better ({candidate['quality']} vs {active['quality']}, p={p:.3f})")
    if not gains:
        return False, "no better than the active model"
    return True, "; ".join(gains)


# --- Deciding, on their own -----------------------------------------------------------

SCOUT_INTERVAL_S = int(os.environ.get("AIDEN_MODEL_SCOUT_INTERVAL", str(24 * 3600)))
FIRST_SCOUT_AFTER_S = 3600
IDLE_LOAD = 2.0
IDLE_AFTER_CHAT_S = 15 * 60
ROLLBACK_WINDOW_S = 24 * 3600
ROLLBACK_AFTER_FAILURES = 2

_activity = {"last_chat": 0.0}
_scouting = threading.Lock()
switch_counter = metrics.get_meter("aiden").create_counter(
    name="aiden_model_switches", description="Models AIden switched to or rolled back from, by device and action", unit="1")


def note_chat():
    _activity["last_chat"] = time.time()


def idle() -> bool:
    return os.getloadavg()[0] < IDLE_LOAD and time.time() - _activity["last_chat"] > IDLE_AFTER_CHAT_S


def scout(device: str) -> Dict[str, Any]:
    """One round of looking for a better model for a device, and switching if one is found."""
    if not _scouting.acquire(blocking=False):
        return {"outcome": "busy", "reason": "already scouting"}
    try:
        current = state(max_age_s=0)
        if not current or device not in current["devices"]:
            return {"outcome": "skipped", "reason": f"no steward-managed models on the {device}"}
        slots = current["devices"][device]
        if slots.get("trial"):  # left over from an interrupted round
            steward("POST", "/end-trial", {"device": device})
        candidates = catalog(device)
        if not candidates:
            journal("scouted", device=device, outcome="nothing new to try")
            return {"outcome": "nothing new to try"}
        name = source = None
        for candidate in candidates:
            try:
                source, name = candidate["source"], start_trial(candidate["source"], device)
                break
            except StewardError as exc:
                # Not recorded under "source": a limit today (memory, budget) may pass another day
                journal("skipped", device=device, candidate=candidate["source"], reason=str(exc))
                name = None
        if not name:
            return {"outcome": "no candidate could be tried"}
        seed = int(time.time())
        questions = evals.sample(seed) if device == "gpu" else routing_questions()
        problems = measurement_problems(device, questions)
        if problems:
            steward("POST", "/end-trial", {"device": device})
            # Recorded under "candidate", not "source": the model isn't at fault and may be tried again
            journal("measurement_invalid", device=device, candidate=source, name=name, problems=problems)
            return {"outcome": "measurement invalid", "problems": problems}
        result = evaluate(device, name, questions)
        baseline = evaluate(device, slots["active"], questions)
        switch, reason = better(result, baseline)
        opinion = claude_opinion(device, result, baseline)
        replays = judge_replays(device, name, slots["active"], seed) if device == "gpu" else None
        if switch and replays and replays["veto"]:
            switch, reason = False, replays["veto"]
        journal("judged", device=device, source=source, name=name, candidate=result, active=baseline,
                switch=switch, reason=reason, claude=opinion, replays=replays)
        if switch:
            steward("POST", "/activate", {"device": device, "name": name})
            switch_counter.add(1, {"device": device, "action": "switch"})
            journal("switched", device=device, source=source, name=name, previous=slots["active"], reason=reason)
            outcome = "switched"
        else:
            steward("POST", "/end-trial", {"device": device})
            steward("POST", "/delete", {"name": name})
            journal("rejected", device=device, source=source, name=name, reason=reason)
            outcome = "rejected"
        _state["at"] = 0
        return {"outcome": outcome, "candidate": name, "reason": reason, "scores": {"candidate": result, "active": baseline}}
    except (StewardError, requests.RequestException) as exc:
        journal("scout_failed", device=device, reason=f"{type(exc).__name__}: {exc}")
        return {"outcome": "failed", "reason": str(exc)}
    finally:
        _scouting.release()


def watch(backend: str, sensed: Dict[str, Any]):
    """After a switch, a model that keeps failing its probes is rolled back on AIden's own."""
    current = state()
    for device, (name, _) in SERVERS.items():
        if name != backend or not current or device not in current["devices"]:
            continue
        slots = current["devices"][device]
        recent = slots.get("switched_at") and time.time() - slots["switched_at"] < ROLLBACK_WINDOW_S
        if recent and slots.get("previous") and not sensed.get("generating") and sensed.get("failures", 0) >= ROLLBACK_AFTER_FAILURES:
            try:
                steward("POST", "/rollback", {"device": device})
                switch_counter.add(1, {"device": device, "action": "rollback"})
                journal("rolled_back", device=device, name=slots["active"], back_to=slots["previous"],
                        reason=f"failed {sensed['failures']} probes after the switch")
                _state["at"] = 0
            except (StewardError, requests.RequestException) as exc:
                logger.error("Rollback on the %s failed: %s", device, exc)


def recent(days: int = 7) -> List[Dict[str, Any]]:
    """Model decisions from the journal (newest last)."""
    cutoff = time.time() - days * 86400
    found = []
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR)) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if path.endswith(".jsonl"):
            with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
                for line in f:
                    if '"kind": "model"' in line:
                        record = json.loads(line)
                        if datetime.fromisoformat(record["at"]).timestamp() >= cutoff:
                            found.append(record)
    return found


def run_forever():
    """Scout each device once per SCOUT_INTERVAL_S, at a moment the machine is idle."""
    time.sleep(FIRST_SCOUT_AFTER_S)
    last: Dict[str, float] = {}
    while True:
        for device in SERVERS:
            if time.time() - last.get(device, 0) >= SCOUT_INTERVAL_S and idle():
                last[device] = time.time()
                logger.info("Scouted the %s: %s", device, scout(device).get("outcome"))
        time.sleep(600)


def start():
    if STEWARD_TOKEN:
        threading.Thread(target=run_forever, daemon=True, name="model-scout").start()


api = APIRouter()


@api.get("/models", summary="AIden's models: what is active, previous or on trial, and recent decisions")
def models_endpoint():
    return {"steward": state(max_age_s=0), "recent": recent()}


@api.post("/models/scout", summary="Look for a better model for a device now (runs in the background)")
def scout_endpoint(device: str = "npu"):
    if device not in SERVERS:
        return {"error": f"unknown device {device}"}
    threading.Thread(target=scout, args=(device,), daemon=True, name=f"scout-{device}").start()
    return {"started": device}


# --- The user's own conversations as a veto --------------------------------------------

MIN_DECISIVE_VERDICTS = 5


def judge_replays(device: str, candidate: str, active: str, seed: int) -> Optional[Dict[str, Any]]:
    """Replay recent conversations on both models and let two judges compare the answers.
    Claude can veto a switch when it clearly prefers the active model and the local judge
    agrees; the local judge alone can't (it is the active model, so it is biased)."""
    from router import split_confidence
    prompts = evals.replay_prompts()
    if not prompts:
        return None
    pairs = []
    for turn in prompts:
        try:
            pairs.append({"prompt": turn["prompt"], "disliked": turn["disliked"],
                          "candidate": split_confidence(ask_answer(device, candidate, turn["prompt"]))[0],
                          "active": split_confidence(ask_answer(device, active, turn["prompt"]))[0]})
        except Exception as exc:
            logger.info("Replay failed: %s", exc)
    local = evals.local_verdicts(lambda q: plain_reply(device, active, q, 8), pairs, seed)
    shareable = [p for p in pairs if evals.shareable(p)[0]]
    claude = evals.claude_verdicts(shareable, seed)
    result = {"replayed": len(pairs), "disliked": sum(p["disliked"] for p in pairs),
              "shared_with_claude": len(shareable), "local": evals.tally(local), "claude": evals.tally(claude), "veto": None}
    c = result["claude"]
    if c and c["active"] + c["candidate"] >= MIN_DECISIVE_VERDICTS:
        p = p_better([v == "active" for v in claude], [v == "candidate" for v in claude])
        if p <= SIGNIFICANCE and result["local"]["active"] > result["local"]["candidate"]:
            result["veto"] = (f"on your conversations both judges prefer the current model "
                              f"(Claude {c['active']}-{c['candidate']}, local {result['local']['active']}-{result['local']['candidate']})")
    return result
