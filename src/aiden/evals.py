"""Measuring models on harder tests and on the user's own conversations (layer 2).

- Public test sets, fetched once from Hugging Face and cached in EVAL_DIR, checked
  automatically: GSM8K (maths word problems, numeric answers) and MMLU-Pro (10-option
  multiple choice across many fields). Both MIT-licensed. Each round samples the same
  questions for the candidate and the active model, so results can be compared per question.
- Replays of the user's past conversations, judged pairwise by two judges: the active
  model (local, biased toward its own style) and Claude as mentor. Turns rated thumbs-down
  come first. Only turns that didn't use the user's notes are replayed, and every prompt
  and answer must pass the vault-similarity guard before Claude sees it. The judges can
  only veto a switch, never cause one.
"""
import json
import logging
import os
import random
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

import experience

EVAL_DIR = os.path.join(experience.EXPERIENCE_DIR, "evalsets")
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASETS = {  # name: (dataset, config, how many rows to keep)
    "gsm8k": ("openai/gsm8k", "main", 400),
    "mmlu_pro": ("TIGER-Lab/MMLU-Pro", "default", 400),
}
PER_ROUND = {"gsm8k": 30, "mmlu_pro": 30}
LETTERS = "ABCDEFGHIJ"
REPLAYS = 10

logger = logging.getLogger("aiden.evals")


# --- Public test sets -----------------------------------------------------------------

def fetch(name: str) -> List[Dict[str, Any]]:
    """Rows of a test set, spread across it (MMLU-Pro is ordered by subject)."""
    dataset, config, keep = DATASETS[name]
    first = requests.get(ROWS_API, timeout=60, params={
        "dataset": dataset, "config": config, "split": "test", "offset": 0, "length": 1}).json()
    total = first["num_rows_total"]
    rows = []
    for offset in range(0, total, max(total // (keep // 100), 100))[:keep // 100]:
        page = requests.get(ROWS_API, timeout=60, params={
            "dataset": dataset, "config": config, "split": "test", "offset": offset, "length": 100}).json()
        rows += [r["row"] for r in page["rows"]]
    return rows


def load(name: str) -> List[Dict[str, Any]]:
    path = os.path.join(EVAL_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    rows = fetch(name)
    os.makedirs(EVAL_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return rows


def sample(seed: int) -> Dict[str, List[Dict[str, Any]]]:
    """The questions of one round, the same for every model judged in it."""
    rng = random.Random(seed)
    return {name: rng.sample(load(name), PER_ROUND[name]) for name in DATASETS}


def gsm8k_truth(row: Dict[str, Any]) -> float:
    return float(row["answer"].split("####")[-1].strip().replace(",", ""))


def gsm8k_answer(text: str) -> Optional[float]:
    match = re.search(r"Answer:\s*\$?\s*(-?[\d,]*\.?\d+)", text) or None
    numbers = [match.group(1)] if match else re.findall(r"-?[\d,]*\.?\d+", text)
    try:
        return float(numbers[-1].replace(",", "")) if numbers else None
    except ValueError:
        return None


def mmlu_prompt(row: Dict[str, Any]) -> str:
    options = row["options"] if isinstance(row["options"], list) else json.loads(row["options"].replace("'", '"'))
    lines = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    return f"{row['question']}\n\n{lines}\n\nAnswer with only the letter of the correct option."


def mmlu_answer(text: str) -> Optional[str]:
    """The chosen option letter: a reply of just the letter, "the answer is X", or a line
    starting "X." / "(X)". Not any capital letter in the text: "I don't know" isn't option I."""
    text = text.strip()
    match = re.fullmatch(r"\W*([A-J])\W*", text)
    if match:
        return match.group(1)
    match = (re.search(r"(?:answer|option)\s*(?:is|:)?\s*\(?\**([A-J])\b", text, re.I)
             or re.search(r"^\W*\(?([A-J])[.)]", text, re.M))
    return match.group(1).upper() if match else None


def checked_outcomes(ask: Callable[[str, int], str], questions: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[bool]]:
    """Per question: right or wrong. ask(prompt, max_tokens) returns the model's reply."""
    outcomes: Dict[str, List[bool]] = {"gsm8k": [], "mmlu_pro": []}
    for row in questions.get("gsm8k", []):
        try:
            reply = ask(f"{row['question']}\nSolve it briefly, then end with a line 'Answer: <number>'.", 512)
            got = gsm8k_answer(reply)
            outcomes["gsm8k"].append(got is not None and abs(got - gsm8k_truth(row)) < 1e-6)
        except Exception:
            outcomes["gsm8k"].append(False)
    for row in questions.get("mmlu_pro", []):
        try:
            outcomes["mmlu_pro"].append(mmlu_answer(ask(mmlu_prompt(row), 8)) == row["answer"])
        except Exception:
            outcomes["mmlu_pro"].append(False)
    return outcomes


# --- The user's own conversations -----------------------------------------------------

def replay_prompts(limit: int = REPLAYS) -> List[Dict[str, Any]]:
    """Recent turns that didn't use the user's notes, thumbs-down ones first."""
    turns, disliked = {}, set()
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR)) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if not path.endswith(".jsonl"):
            continue
        with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                answer = record.get("answer") if isinstance(record.get("answer"), dict) else {}
                prompt = record.get("prompt") or ""
                if (record.get("kind") == "turn" and answer.get("source") == "local" and not answer.get("used_notes")
                        and prompt and not prompt.lstrip().startswith("###") and len(prompt) < 2000):
                    turns[prompt] = {"prompt": prompt, "trace_id": record.get("trace_id"), "disliked": False}
                if record.get("kind") == "feedback" and record.get("rating") == "down" and record.get("trace_id"):
                    disliked.add(record["trace_id"])
    for turn in turns.values():
        turn["disliked"] = turn["trace_id"] in disliked
    ordered = sorted(turns.values(), key=lambda t: not t["disliked"])
    return ordered[:limit]


JUDGE_INSTRUCTION = ("Compare two answers to the same user message. Which is more correct and helpful? "
                     "Reply with only A, B or tie.")


def local_verdicts(judge: Callable[[str], str], pairs: List[Dict[str, Any]], seed: int) -> List[str]:
    """The local judge's verdict per pair, as 'candidate', 'active' or 'tie'. The order of
    the two answers is shuffled per pair, so a judge that prefers 'A' isn't rewarded."""
    rng = random.Random(seed)
    verdicts = []
    for pair in pairs:
        flipped = rng.random() < 0.5
        first, second = (pair["active"], pair["candidate"]) if flipped else (pair["candidate"], pair["active"])
        reply = judge(f"{JUDGE_INSTRUCTION}\n\nUser message:\n{pair['prompt']}\n\nAnswer A:\n{first}\n\nAnswer B:\n{second}")
        choice = (re.search(r"\b(A|B|tie)\b", reply, re.I) or [None, "tie"])[1].lower()
        if choice == "tie":
            verdicts.append("tie")
        else:
            verdicts.append({"a": "active" if flipped else "candidate", "b": "candidate" if flipped else "active"}[choice])
    return verdicts


def claude_verdicts(pairs: List[Dict[str, Any]], seed: int) -> Optional[List[str]]:
    """Claude's verdicts, in one mentor call. None when the mentor isn't available."""
    import mentor
    if not mentor.MENTOR_TOKEN or not pairs:
        return None
    rng = random.Random(seed + 1)
    flips = [rng.random() < 0.5 for _ in pairs]
    items = []
    for i, (pair, flipped) in enumerate(zip(pairs, flips), 1):
        first, second = (pair["active"], pair["candidate"]) if flipped else (pair["candidate"], pair["active"])
        items.append(f"#{i}\nUser message: {pair['prompt']}\nAnswer A: {first}\nAnswer B: {second}")
    question = ("For each numbered item, two assistants answered the same user message. Which answer is more "
                "correct and helpful? Reply with only a JSON list with one entry per item, each \"A\", \"B\" or "
                "\"tie\", in order.\n\n" + "\n\n".join(items))
    try:
        reply = mentor.ask_mentor(question, "", [])["answer"]
        choices = json.loads(reply[reply.find("["):reply.rfind("]") + 1])
    except Exception as exc:
        logger.info("No verdicts from the mentor: %s", exc)
        return None
    if len(choices) != len(pairs):
        return None
    out = []
    for choice, flipped in zip(choices, flips):
        choice = str(choice).strip().lower()
        out.append("tie" if choice not in ("a", "b") else
                   {"a": "active" if flipped else "candidate", "b": "candidate" if flipped else "active"}[choice])
    return out


def shareable(pair: Dict[str, Any]) -> Tuple[bool, str]:
    """May this replay go to Claude? Prompt and both answers must pass the vault guard."""
    import mentor
    for part in ("prompt", "candidate", "active"):
        safe, why, _ = mentor.draft_privacy(pair[part])
        if not safe:
            return False, f"{part}: {why}"
    return True, "ok"


def tally(verdicts: Optional[List[str]]) -> Optional[Dict[str, int]]:
    if verdicts is None:
        return None
    return {k: verdicts.count(k) for k in ("candidate", "active", "tie")}
