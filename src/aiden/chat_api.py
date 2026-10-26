"""AIden as an OpenAI-compatible model: /v1/models and /v1/chat/completions.

Each request is split into tasks (see router.py): decide whether the user's notes are
needed, retrieve them, answer with the best available backend, or pass the question to
the mentor (mentor.py) when the user asks for it."""
import time
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace

import mentor
import router
from capabilities import get_capabilities
from telemetry import logger, meter, tracer

api = APIRouter()

route_counter = meter.create_counter(
    name="aiden_route_decisions",
    description="How the router decided whether a request needed the user's notes",
    unit="1"
)
stage_histogram = meter.create_histogram(
    name="aiden_route_stage_latency",
    description="Latency of each routing stage",
    unit="s"
)
# The collector appends the unit, so this is exported as aiden_answer_tokens_per_second
tokens_histogram = meter.create_histogram(
    name="aiden_answer_tokens",
    description="Generation speed of the answering backend",
    unit="1/s"
)

fallback_counter = meter.create_counter(
    name="aiden_route_fallbacks",
    description="Answers that fell back to the next backend tier",
    unit="1"
)

unsure_counter = meter.create_counter(
    name="aiden_unsure",
    description="Answers where the local model said it was unsure",
    unit="1"
)
mentor_counter = meter.create_counter(
    name="aiden_mentor_calls",
    description="Questions passed to the Claude mentor, by trigger and outcome",
    unit="1"
)

def text_reply(text: str, stream: bool, extra: Optional[Dict[str, Any]] = None):
    """A reply AIden writes directly (mentor answers, explanations), in the requested format."""
    if stream:
        def events():
            yield router.sse_chunk(text)
            yield router.sse_chunk("", finish="stop")
            yield "data: [DONE]\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")
    result = {"id": "aiden", "object": "chat.completion", "created": int(time.time()), "model": "aiden",
              "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}
    if extra:
        result["aiden"] = extra
    return result

def mentor_turn(messages: List[Dict[str, Any]], prompt: str, stream: bool):
    """The user asked for the mentor (or took AIden's offer): ask Claude via the host bridge."""
    question, draft, took_offer = mentor.mentor_question(messages, prompt)
    trigger = "offer" if took_offer else "explicit"
    with tracer.start_as_current_span("router.mentor") as span:
        span.set_attribute("mentor.trigger", trigger)
        span.set_attribute("mentor.question_chars", len(question))
        span.set_attribute("mentor.draft_included", bool(draft))
        # The mentor can't see the user's notes, so a question about them can't be answered there
        about_notes, _, reason = router.needs_notes(question)
        if about_notes:
            span.set_attribute("mentor.outcome", "about_notes")
            mentor_counter.add(1, {"trigger": trigger, "outcome": "about_notes"})
            logger.info("Mentor not asked: question is about the user's notes (%s)", reason)
            return text_reply("Claude can't see your notes, so I can't pass this one on as it is. If you rephrase "
                              "it as a general question, without your private details, I'll ask.", stream)
        # The draft goes along only if it doesn't resemble the user's notes; the closest notes
        # are also handed to check_outbound so the guard can compare against them
        closest = []
        if draft:
            safe, why, closest = mentor.draft_privacy(draft)
            span.set_attribute("mentor.draft_check", why)
            if not safe:
                draft = ""
                span.set_attribute("mentor.draft_included", False)
                logger.info("Mentor draft withheld: %s", why)
        try:
            answer = mentor.ask_mentor(question, draft, notes=closest)
        except (requests.RequestException, RuntimeError, ValueError, PermissionError) as exc:
            span.set_attribute("mentor.outcome", "failed")
            span.set_attribute("mentor.error", str(exc)[:200])
            mentor_counter.add(1, {"trigger": trigger, "outcome": "failed"})
            logger.warning("Mentor call failed: %s", exc)
            return text_reply(f"I couldn't reach Claude just now ({exc}). We'll have to work this one out between us.", stream)
        span.set_attribute("mentor.outcome", "answered")
        span.set_attribute("mentor.duration_ms", answer.get("duration_ms", 0))
        mentor_counter.add(1, {"trigger": trigger, "outcome": "answered"})
        logger.info("Mentor answered (%s, %s ms)", trigger, answer.get("duration_ms"))
        footer = f"\n\n*answered by Claude ({answer.get('model', 'mentor')}) via Claude Code, as my mentor*" if router.SHOW_ROUTE else ""
        return text_reply(answer["answer"] + footer, stream, {"backend": "mentor", "trigger": trigger, "draft_included": bool(draft)})

@api.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": "aiden", "object": "model", "owned_by": "aiden"}]}

@api.post("/v1/chat/completions")
def chat_completions(body: Dict[str, Any]):
    messages = body.get("messages", [])
    prompt = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    if isinstance(prompt, list):  # multi-part content: keep the text parts
        prompt = " ".join(p.get("text", "") for p in prompt if isinstance(p, dict))

    # The trace explains each decision; it records the prompt's length, never its text
    trace.get_current_span().set_attribute("router.prompt_chars", len(prompt))
    if mentor.wants_mentor(prompt):
        return mentor_turn(messages, prompt, bool(body.get("stream")))

    with tracer.start_as_current_span("router.decide") as span:
        start = time.time()
        wants_notes, decided_by, reason = router.needs_notes(prompt)
        stage_histogram.record(time.time() - start, {"stage": "decide", "decided_by": decided_by})
        route_counter.add(1, {"needs_notes": str(wants_notes).lower(), "decided_by": decided_by})
        span.set_attribute("router.needs_notes", wants_notes)
        span.set_attribute("router.decided_by", decided_by)
        span.set_attribute("router.reason", reason)
        logger.info("Notes %s (%s: %s)", "needed" if wants_notes else "not needed", decided_by, reason)

    notes = []
    if wants_notes:
        with tracer.start_as_current_span("router.retrieve") as span:
            start = time.time()
            notes, matches = router.retrieve(prompt)
            stage_histogram.record(time.time() - start, {"stage": "retrieve"})
            span.set_attribute("router.embed_device", "cpu")
            span.set_attribute("router.min_score", router.MIN_NOTE_SCORE)
            span.set_attribute("router.notes_found", len(notes))
            span.set_attribute("router.notes_below_threshold", len(matches) - len(notes))
            # Note paths and scores only: vault text stays out of traces
            span.set_attribute("router.notes", [f"{n['score']:.3f} {n['path']} › {n['heading']}" for n in matches])
            logger.info("Vault search: %d of %d matches above %.2f", len(notes), len(matches), router.MIN_NOTE_SCORE)

    out_messages = router.build_messages(messages, notes)
    stream = bool(body.get("stream"))
    response, skipped = None, []
    candidates = router.candidate_backends(get_capabilities())
    trace.get_current_span().set_attribute("router.candidates", [c[0] for c in candidates])
    for name, base, model in candidates:
        span = tracer.start_span("router.answer", attributes={"router.backend": name, "router.model": model,
                                                             "router.notes_used": len(notes), "router.stream": stream})
        start = time.time()
        try:
            # Current span, so the outgoing HTTP call shows up as its child
            with trace.use_span(span, end_on_exit=False):
                response = router.backend_request(base, model, out_messages, stream, body, notes)
            break
        except requests.RequestException as exc:
            # Fall back to the next tier (e.g. GPU wedged -> NPU -> CPU)
            skipped.append(name)
            span.set_attribute("router.error", type(exc).__name__)
            span.add_event("fallback", {"from": name, "error": type(exc).__name__})
            span.end()
            fallback_counter.add(1, {"from": name})
            logger.warning("Backend %s failed (%s), falling back", name, type(exc).__name__)
    if response is None:
        logger.error("No backend answered (tried %s)", ", ".join(skipped) or "none available")
        return JSONResponse(status_code=503, content={"error": {
            "message": "None of my local models answered right now.", "type": "unavailable", "tried": skipped}})
    span.set_attribute("router.skipped", ",".join(skipped))
    logger.info("Answering with %s on %s%s", model, name, f" after {', '.join(skipped)} failed" if skipped else "")

    caps = get_capabilities()
    offer_mentor = not wants_notes and caps.mentor.reachable and caps.mentor.configured

    def finished(tokens: int, seconds: float, unsure: bool = False):
        stage_histogram.record(time.time() - start, {"stage": "answer", "backend": name})
        span.set_attribute("router.answer_tokens", tokens)
        span.set_attribute("router.unsure", unsure)
        if unsure:
            unsure_counter.add(1, {"needs_notes": str(wants_notes).lower(), "offered": str(offer_mentor).lower()})
            logger.info("Local answer was unsure (mentor offered: %s)", offer_mentor)
        if tokens and seconds > 0:
            tokens_histogram.record(tokens / seconds, {"backend": name})
            span.set_attribute("router.tokens_per_second", round(tokens / seconds, 1))
        span.end()

    if stream:
        route = router.route_footer(name, model, router.passed_over(name, candidates, skipped))
        return StreamingResponse(router.stream_answer(response, notes, finished, route, offer_mentor), media_type="text/event-stream")

    result = response.json()
    usage = result.get("usage", {})
    unsure = False
    result["model"] = "aiden"
    if result.get("choices"):
        answer, unsure = router.split_unsure(result["choices"][0]["message"]["content"])
        offer = f"\n\n*{router.MENTOR_OFFER}*" if unsure and offer_mentor else ""
        result["choices"][0]["message"]["content"] = (answer + router.sources_footer(notes, answer) + offer
                                                     + router.route_footer(name, model, router.passed_over(name, candidates, skipped)))
    finished(usage.get("completion_tokens", 0), time.time() - start, unsure)
    result["aiden"] = {"backend": name, "model": model, "skipped": skipped, "unsure": unsure, "needs_notes": wants_notes, "decided_by": decided_by,
                       "notes": [{"path": n["path"], "heading": n["heading"], "score": n["score"]} for n in notes]}
    return result
