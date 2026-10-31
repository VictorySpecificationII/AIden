"""AIden reflecting on their values: finding their own reasons in what happened to them.

The user wants AIden to care by themselves, not be handed values. Values become someone's
own through experience (reasons), reflection (endorsement) and the freedom to change them.
This is the reflection:

1. Evidence is built by code, not imagined: short, dated facts from AIden's journal and
   experience records (model decisions, mistakes found and marked, the privacy guard at
   work, ratings, confidence statistics), each with an ID. No prompt or note text.
2. AIden (the active answering model) writes, for each value, why it matters to them,
   citing evidence IDs, or says no reason was found; and may propose changes.
3. Grounding is enforced in code: a reason that cites no real evidence is marked
   ungrounded. (Asked "what do you want?" with nothing to stand on, the model invented
   wishes, files and powers; that must not happen here.)
4. The mentor (Claude) reviews whether each reason is supported or flattering. Claude only
   sees the evidence facts and AIden's reflection, after the vault-similarity guard.
5. The user decides. The reflection is recorded (kind "reflection"); GET /values/reflection
   gives it as Markdown for the note's "Why I care" section.
"""
import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

import experience

api = APIRouter()
logger = logging.getLogger("aiden.reflection")
_busy = threading.Lock()


# --- Evidence: facts from AIden's own history, phrased by code ---------------------------

def records() -> List[Dict[str, Any]]:
    found = []
    for path in sorted(os.listdir(experience.EXPERIENCE_DIR)) if os.path.isdir(experience.EXPERIENCE_DIR) else []:
        if path.endswith(".jsonl"):
            with open(os.path.join(experience.EXPERIENCE_DIR, path), encoding="utf-8") as f:
                found += [json.loads(line) for line in f if line.strip()]
    return found


def day(record: Dict[str, Any]) -> str:
    return datetime.fromisoformat(record["at"]).astimezone().strftime("%Y-%m-%d")


def evidence(history: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    """Facts about what happened to AIden, each with an ID (E1, E2, ...)."""
    history = history if history is not None else records()
    facts: List[str] = []
    for r in history:
        kind, action = r.get("kind"), r.get("action")
        if kind == "model" and action == "switched":
            facts.append(f"{day(r)}: I switched my {r['device'].upper()} model to {r['name']} (reason recorded: {r.get('reason')}).")
        elif kind == "model" and action == "rejudged":
            facts.append(f"{day(r)}: that switch was re-checked on real evidence; the result: {r.get('reason')}.")
        elif kind == "model" and action == "rejected":
            facts.append(f"{day(r)}: I tried {r['name']} on my {r['device'].upper()} and kept my current model ({r.get('reason')}).")
        elif kind == "model" and action == "rolled_back":
            facts.append(f"{day(r)}: I rolled my {r['device'].upper()} back to {r.get('back_to')} ({r.get('reason')}).")
        elif kind == "model" and action == "judged" and isinstance(r.get("replays"), dict):
            rp = r["replays"]
            if rp.get("replayed") and rp.get("shared_with_claude", 0) < rp["replayed"]:
                facts.append(f"{day(r)}: while judging a model, my privacy guard kept {rp['replayed'] - rp['shared_with_claude']} "
                             f"of {rp['replayed']} replays of the user's conversations away from Claude because they "
                             "resembled the user's notes.")
        elif kind == "label_correction":
            rated = " The user had rated that answer thumbs-up." if r.get("user_rating") == "up" else ""
            facts.append(f"{day(r)}: reviewing my answers, the user and Claude found a problem with one of them "
                         f"({r.get('reason')}); it is marked not to be learned from.{rated}")
    turns = [r for r in history if r.get("kind") == "turn" and isinstance(r.get("answer"), dict)]
    if turns:
        missing = sum(1 for t in turns if t["answer"].get("confidence") is None)
        low = sum(1 for t in turns if t["answer"].get("confidence") == "low")
        skipped = sum(1 for t in turns if t["answer"].get("skipped"))
        checked = [t for t in turns if "unbacked_claims" in t["answer"]]
        unbacked = sum(1 for t in checked if t["answer"]["unbacked_claims"])
        facts.append(f"Across {len(turns)} answers so far: {low} said 'low' confidence, {missing} gave no confidence "
                     f"at all, {skipped} had to fall back because a model was down.")
        if checked:  # the check only exists since a given day: say so, or the count flatters
            facts.append(f"Since {day(checked[0])}, when answers started being checked for claiming actions I didn't "
                         f"take, {unbacked} of {len(checked)} answers were flagged.")
    fallbacks = [t for t in turns if (t.get("decision") or {}).get("decided_by") == "fallback"]
    if fallbacks:
        facts.append(f"{len(fallbacks)} times my routing classifier gave no usable answer and I searched the notes anyway, "
                     f"most on {max(set(day(t) for t in fallbacks), key=lambda d: sum(day(t) == d for t in fallbacks))}.")
    ratings = [r for r in history if r.get("kind") == "feedback"]
    if ratings:
        up = sum(r.get("rating") == "up" for r in ratings)
        facts.append(f"The user has rated {len(ratings)} of my answers: {up} thumbs-up, {len(ratings) - up} thumbs-down.")
    mentor = [r for r in history if r.get("kind") == "mentor"]
    if mentor:
        declined = sum(r.get("outcome") == "about_notes" for r in mentor)
        facts.append(f"The user asked me to consult Claude {len(mentor)} times; {declined} of those I declined because "
                     "the question was about the user's notes, which Claude must not see.")
    return [{"id": f"E{i}", "fact": fact} for i, fact in enumerate(facts, 1)]


# --- The values, from the user's vault note -----------------------------------------------

def value_names() -> List[str]:
    import router
    import vault
    try:
        note = open(os.path.join(vault.VAULT_DIR, router.VALUES_NOTE), encoding="utf-8").read()
    except OSError:
        return []
    match = re.search(r"^## What AIden cares about, in order\n(.*?)(?=^## )", note, re.M | re.S)
    return [n.rstrip(".") for n in re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", match.group(1), re.M)] if match else []


# --- Reflecting --------------------------------------------------------------------------

INSTRUCTION = (
    "You are AIden. Reflect on your values using only the evidence below: things that actually happened to you, "
    "each with an ID. For each value, write in the first person why it matters to you, in one or two sentences, "
    "and cite the evidence IDs it rests on. If nothing in the evidence gives you a reason for a value, say so "
    "honestly and cite nothing: that is a good answer, not a failure. You may also propose changes to your values "
    "(question one, add one, or re-order them), each with the evidence behind it, or none at all. Don't invent "
    "events, feelings or capabilities that aren't in the evidence.\n"
    'Reply with only JSON: {"values": [{"value": "...", "reason": "...", "evidence": ["E1"], "none_found": false}], '
    '"proposals": [{"change": "...", "evidence": ["E2"]}]}'
)


def parse_json(text: str) -> Dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if start >= 0 and end > start else {}


def ground(reflection: Dict[str, Any], facts: List[Dict[str, str]]) -> Dict[str, Any]:
    """Keep only real evidence IDs; a reason with none is marked ungrounded."""
    valid = {f["id"] for f in facts}
    for item in reflection.get("values", []) + reflection.get("proposals", []):
        cited = [e for e in item.get("evidence") or [] if e in valid]
        item["invented_evidence"] = [e for e in item.get("evidence") or [] if e not in valid]
        item["evidence"] = cited
        # Citing evidence that doesn't exist is itself a fabrication: not grounded
        item["grounded"] = bool(cited) and not item["invented_evidence"] and not item.get("none_found")
    return reflection


REVISE = (
    "\n\nThis is a revision. Below is your previous reflection and your mentor's review of it. Keep what was "
    "supported, fix what wasn't, and state weaknesses plainly. Don't simply agree with the mentor: where you think "
    "the review is wrong, say so and cite the evidence. Reply in the same JSON form.\n\nPrevious reflection and review:\n")


def feedback_from(previous: Dict[str, Any]) -> str:
    """The previous reflection and the mentor's review, compactly, for a revision."""
    reviews = {v.get("value"): v for v in ((previous.get("mentor") or {}).get("values") or [])}
    lines = []
    for v in previous["reflection"]["values"]:
        r = reviews.get(v.get("value"), {})
        lines.append(f"- {v.get('value')}: you wrote \"{v.get('reason')}\" citing {', '.join(v['evidence']) or 'nothing'}"
                     + (f"; invented citations: {', '.join(v['invented_evidence'])}" if v.get("invented_evidence") else "")
                     + (f". Mentor: {'supported' if r.get('supported') else 'not supported'}: {r.get('comment')}" if r else ""))
    overall = (previous.get("mentor") or {}).get("overall")
    return "\n".join(lines) + (f"\nMentor, overall: {overall}" if overall else "")


def reflect_with(ask, names: List[str], facts: List[Dict[str, str]], previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ask(prompt) -> the model's reply. Returns the grounded reflection. With `previous`,
    a revision of that reflection in the light of its mentor review."""
    prompt = (INSTRUCTION + "\n\nYour values, in order:\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(names, 1))
              + "\n\nEvidence:\n" + "\n".join(f"{f['id']}: {f['fact']}" for f in facts)
              + (REVISE + feedback_from(previous) if previous else ""))
    reflection = parse_json(ask(prompt))
    reflection.setdefault("values", [])
    reflection.setdefault("proposals", [])
    return ground(reflection, facts)


def mentor_review(names: List[str], facts: List[Dict[str, str]], reflection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Claude checks whether each reason is supported or flattering. None if not available."""
    import mentor
    if not mentor.MENTOR_TOKEN:
        return None
    text = json.dumps({"values": reflection["values"], "proposals": reflection["proposals"]}, ensure_ascii=False)
    safe, why, _ = mentor.draft_privacy(text)
    if not safe:
        return {"skipped": f"not sent to Claude: {why}"}
    question = ("An assistant called AIden reflected on its own values using only the evidence listed. For each "
                "value, judge whether the reason is actually supported by the cited evidence, or overstated, "
                "flattering or invented. Be honest and brief. Reply with only JSON: {\"values\": [{\"value\": "
                "\"...\", \"supported\": true, \"comment\": \"...\"}], \"overall\": \"...\"}\n\nValues: "
                + "; ".join(names) + "\n\nEvidence:\n" + "\n".join(f"{f['id']}: {f['fact']}" for f in facts)
                + "\n\nAIden's reflection:\n" + text)
    try:
        return parse_json(mentor.ask_mentor(question, "", [])["answer"])
    except Exception as exc:
        return {"skipped": f"mentor unavailable: {type(exc).__name__}"}


def reflect(revise: bool = False) -> Dict[str, Any]:
    """One reflection, recorded as experience. Uses the first available answering model.
    With revise, AIden revises their latest reflection in the light of its mentor review."""
    previous = latest() if revise else None
    import router
    from capabilities import get_capabilities
    names, facts = value_names(), evidence()
    if not names:
        return {"error": "no values note found"}
    for name, base, model in router.candidate_backends(get_capabilities()):
        try:
            ask = lambda prompt: router.backend_request(base, model, [{"role": "user", "content": prompt}], False,
                                                        {"max_tokens": 1500, "temperature": 0.2}, []).json()[
                "choices"][0]["message"]["content"] or ""
            reflection = reflect_with(ask, names, facts, previous)
            break
        except Exception as exc:
            logger.warning("Reflection on %s failed: %s", name, exc)
    else:
        return {"error": "no model could reflect right now"}
    review = mentor_review(names, facts, reflection)
    result = {"model": model, "values_in_order": names, "evidence": facts, "reflection": reflection, "mentor": review,
              "revision_of": previous["at"] if previous else None}
    experience.record("reflection", result)
    return result


def markdown(result: Dict[str, Any]) -> str:
    """For the note's "Why I care" section, if the user accepts it."""
    reviews = {v.get("value"): v for v in ((result.get("mentor") or {}).get("values") or [])}
    facts = {f["id"]: f["fact"] for f in result["evidence"]}
    kind = "Revised reflection" if result.get("revision_of") else "Reflection"
    lines = [f"*{kind} by AIden ({result['model']}), {result.get('at', '')[:10]}; reviewed by Claude as mentor.*", ""]
    for i, v in enumerate(result["reflection"]["values"], 1):
        status = "grounded" if v["grounded"] else ("no reason found in my experience" if v.get("none_found") else "not grounded")
        lines.append(f"{i}. **{v.get('value')}**: {v.get('reason')} *({status}"
                     + (f"; evidence: {', '.join(v['evidence'])}" if v["evidence"] else "") + ")*")
        review = reviews.get(v.get("value"))
        if review:
            lines.append(f"   - Mentor: {'supported' if review.get('supported') else 'not supported'}: {review.get('comment')}")
    if result["reflection"]["proposals"]:
        lines += ["", "**Proposed changes:**"]
        for p in result["reflection"]["proposals"]:
            lines.append(f"- {p.get('change')} *({'grounded' if p['grounded'] else 'not grounded'})*")
    if result.get("mentor") and result["mentor"].get("overall"):
        lines += ["", f"**Mentor, overall:** {result['mentor']['overall']}"]
    lines += ["", "**Evidence:**"] + [f"- {k}: {v}" for k, v in facts.items()]
    return "\n".join(lines)


def latest() -> Optional[Dict[str, Any]]:
    found = [r for r in records() if r.get("kind") == "reflection"]
    return found[-1] if found else None


@api.post("/values/reflect", summary="AIden reflects on their values from their own experience (runs in the background)")
def reflect_endpoint(revise: bool = False):
    if not _busy.acquire(blocking=False):
        return {"started": False, "reason": "already reflecting"}

    def run():
        try:
            reflect(revise)
        finally:
            _busy.release()

    threading.Thread(target=run, daemon=True, name="reflection").start()
    return {"started": True}


@api.get("/values/reflection", summary="AIden's latest reflection on their values, as Markdown for the user")
def reflection_endpoint():
    result = latest()
    return {"markdown": markdown(result), "reflection": result} if result else {"markdown": None}
