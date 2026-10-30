"""Shadow mode (judgement layer 3b): a candidate proves itself on real traffic first.

A candidate that wins its judgement doesn't take over at once. It stays loaded (the
steward's trial slot) and, after each real answer, silently answers the same thing in
the background; only the active model's answers are ever shown. The pairs are stored
locally (EXPERIENCE_DIR/shadow/<device>.jsonl). After SHADOW_DAYS and MIN_PAIRS AIden
decides:
- GPU (answers): the local judge and Claude compare the pairs; Claude clearly preferring
  the current model, with the local judge agreeing, vetoes the switch;
- NPU (routing): where the two disagreed, Claude says which was right; the current model
  being right clearly more often vetoes the switch.
Claude only sees pairs that pass the vault-similarity guard. With no evidence against the
candidate after MAX_DAYS, it switches on the strength of its benchmarks. If free memory
falls below the steward's floor, the shadow ends early and decides with what it has.
The shadow's state lives in the journal, so it survives AIden restarting.
"""
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import evals
import experience

SHADOW_DAYS = float(os.environ.get("AIDEN_MODEL_SHADOW_DAYS", "2"))
MAX_DAYS = 7
MIN_PAIRS = 10
MAX_PAIRS = 50
MIN_FREE_GB = float(os.environ.get("AIDEN_MODEL_MIN_FREE_GB", "4"))

logger = logging.getLogger("aiden.shadow")
_busy = threading.Lock()  # one background shadow job at a time


def path(device: str) -> str:
    return os.path.join(experience.EXPERIENCE_DIR, "shadow", f"{device}.jsonl")


def active(device: str) -> Optional[Dict[str, Any]]:
    """The shadow running on a device, from the journal: the last shadow_started with no
    shadow_ended after it."""
    import models
    current = None
    for record in models.recent(days=MAX_DAYS + 1):
        if record.get("device") != device:
            continue
        if record["action"] == "shadow_started":
            current = record
        elif record["action"] == "shadow_ended":
            current = None
    return current


def pairs(device: str) -> List[Dict[str, Any]]:
    try:
        with open(path(device), encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except OSError:
        return []


def store(device: str, pair: Dict[str, Any]):
    os.makedirs(os.path.dirname(path(device)), exist_ok=True)
    with open(path(device), "a", encoding="utf-8") as f:
        f.write(json.dumps(pair, ensure_ascii=False) + "\n")


def in_background(job, *args):
    """Run a shadow job after the user's answer, never alongside another one."""
    if not _busy.acquire(blocking=False):
        return

    def run():
        try:
            job(*args)
        except Exception as exc:  # the shadow must never affect the user
            logger.info("Shadow job failed: %s", exc)
        finally:
            _busy.release()

    threading.Thread(target=run, daemon=True, name="shadow").start()


def observe_answer(messages: List[Dict[str, Any]], prompt: str, answer: str, used_notes: bool, trace_id: Optional[str]):
    """After a real GPU answer: the GPU candidate answers the same messages, silently."""
    shadow = active("gpu")
    if not shadow or len(pairs("gpu")) >= MAX_PAIRS or not answer:
        return

    def job():
        import models
        from router import backend_request, split_confidence
        _, server = models.SERVERS["gpu"]
        response = backend_request(f"{server}/v3", shadow["name"], messages, False, {"max_tokens": 1024}, [])
        candidate = split_confidence(response.json()["choices"][0]["message"]["content"] or "")[0]
        store("gpu", {"at": time.time(), "trace_id": trace_id, "prompt": prompt, "used_notes": used_notes,
                      "active": answer, "candidate": candidate})

    in_background(job)


def observe_route(prompt: str, decision: bool, trace_id: Optional[str]):
    """After a real NPU routing decision: the NPU candidate classifies the same prompt."""
    shadow = active("npu")
    if not shadow or len(pairs("npu")) >= MAX_PAIRS:
        return

    def job():
        from router import classify_with_npu
        candidate = classify_with_npu(prompt, shadow["name"])[0]
        store("npu", {"at": time.time(), "trace_id": trace_id, "prompt": prompt,
                      "active": decision, "candidate": candidate})

    in_background(job)


def claude_labels(prompts: List[str]) -> Optional[List[Optional[bool]]]:
    """Claude's view, per prompt, of whether answering it needs the user's personal notes."""
    import mentor
    if not mentor.MENTOR_TOKEN or not prompts:
        return None
    items = "\n".join(f"#{i} {p}" for i, p in enumerate(prompts, 1))
    question = ("For each numbered message a user sent to their personal assistant: does answering it need the "
                "user's own personal notes (their projects, decisions, clients, plans or past work)? Reply with "
                "only a JSON list of true/false, one per message, in order.\n\n" + items)
    try:
        reply = mentor.ask_mentor(question, "", [])["answer"]
        labels = json.loads(reply[reply.find("["):reply.rfind("]") + 1])
        return [bool(x) if isinstance(x, bool) else None for x in labels] if len(labels) == len(prompts) else None
    except Exception as exc:
        logger.info("No labels from the mentor: %s", exc)
        return None


def verdict(device: str, collected: List[Dict[str, Any]], seed: int) -> Dict[str, Any]:
    """What the real traffic says: {"veto": reason or None, ...details}."""
    import models
    if device == "gpu":
        judged = [p for p in collected if p["active"] and p["candidate"]]
        local = evals.local_verdicts(lambda q: models.plain_reply("gpu", active_model("gpu"), q, 8), judged, seed)
        shareable = [p for p in judged if not p.get("used_notes") and evals.shareable(p)[0]]
        claude = evals.claude_verdicts(shareable, seed)
        result = {"pairs": len(judged), "shared_with_claude": len(shareable),
                  "local": evals.tally(local), "claude": evals.tally(claude), "veto": None}
        c = result["claude"]
        if c and c["active"] + c["candidate"] >= models.MIN_DECISIVE_VERDICTS:
            p = models.p_better([v == "active" for v in claude], [v == "candidate" for v in claude])
            if p <= models.SIGNIFICANCE and result["local"]["active"] > result["local"]["candidate"]:
                result["veto"] = (f"on your real questions both judges preferred the current model "
                                  f"(Claude {c['active']}-{c['candidate']}, local {result['local']['active']}-{result['local']['candidate']})")
        return result
    disagreed = [p for p in collected if p["candidate"] is not None and p["candidate"] != p["active"]]
    shareable = [p for p in disagreed if evals.shareable({"prompt": p["prompt"], "candidate": "", "active": ""})[0]]
    labels = claude_labels([p["prompt"] for p in shareable])
    result = {"decisions": len(collected), "disagreements": len(disagreed), "labelled_by_claude": 0, "veto": None}
    if labels:
        known = [(p, l) for p, l in zip(shareable, labels) if l is not None]
        active_right = [p["active"] == l for p, l in known]
        candidate_right = [p["candidate"] == l for p, l in known]
        result.update(labelled_by_claude=len(known), active_right=sum(active_right), candidate_right=sum(candidate_right))
        if len(known) >= models.MIN_DECISIVE_VERDICTS and models.p_better(active_right, candidate_right) <= models.SIGNIFICANCE:
            result["veto"] = (f"on your real requests the current model routed better where they disagreed "
                              f"({sum(active_right)} vs {sum(candidate_right)} of {len(known)}, labelled by Claude)")
    return result


def active_model(device: str) -> str:
    import models
    return models.state()["devices"][device]["active"]


def check(device: str) -> Optional[Dict[str, Any]]:
    """Decide a shadow that has run long enough (or must end early). Returns the outcome."""
    import models
    shadow = active(device)
    if not shadow:
        return None
    started = models.datetime.fromisoformat(shadow["at"]).timestamp()
    age_days = (time.time() - started) / 86400
    collected = pairs(device)
    low_memory = models.free_memory_gb() < MIN_FREE_GB
    ready = age_days >= SHADOW_DAYS and len(collected) >= MIN_PAIRS
    if not (ready or age_days >= MAX_DAYS or low_memory):
        return None
    result = verdict(device, collected, seed=int(started))
    why_now = "low memory" if low_memory and not ready else ("enough traffic" if ready else "time limit")
    slots = models.state(max_age_s=0)["devices"][device]
    if result["veto"]:
        models.steward("POST", "/end-trial", {"device": device})
        models.steward("POST", "/delete", {"name": shadow["name"]})
        models.journal("shadow_ended", device=device, source=shadow["source"], name=shadow["name"],
                       outcome="rejected", reason=result["veto"], shadow=result, ended_because=why_now)
        models.journal("rejected", device=device, source=shadow["source"], name=shadow["name"], reason=result["veto"])
        outcome = "rejected"
    else:
        evidence = "" if len(collected) >= MIN_PAIRS else f" (shadow inconclusive: {len(collected)} pairs)"
        models.steward("POST", "/activate", {"device": device, "name": shadow["name"]})
        models.switch_counter.add(1, {"device": device, "action": "switch"})
        models.journal("shadow_ended", device=device, source=shadow["source"], name=shadow["name"],
                       outcome="switched", shadow=result, ended_because=why_now)
        models.journal("switched", device=device, source=shadow["source"], name=shadow["name"],
                       previous=slots["active"], reason=shadow["reason"] + evidence)
        outcome = "switched"
    try:
        os.replace(path(device), path(device) + f".{int(time.time())}.done")  # keep, but start fresh next time
    except OSError:
        pass
    models._state["at"] = 0
    return {"outcome": outcome, **result}
