"""Mentor: when to ask Claude, what to send, and keeping the user's notes local."""
import pytest
import requests

import mentor
import router


@pytest.mark.parametrize("prompt", ["ask Claude", "Can you ask your mentor?", "I'd like a second opinion",
                                    "I'm not sure either, ask Claude"])
def test_mentor_requests_are_recognised(prompt):
    assert mentor.wants_mentor(prompt)


@pytest.mark.parametrize("prompt", ["What is Claude Shannon known for?", "explain TCP"])
def test_ordinary_questions_do_not_go_to_the_mentor(prompt):
    assert not mentor.wants_mentor(prompt)


def test_explicit_question_is_sent_without_a_draft():
    question, draft, took_offer = mentor.mentor_question(
        [{"role": "user", "content": "Ask Claude: what is the capital of Australia?"}],
        "Ask Claude: what is the capital of Australia?")
    assert question == "what is the capital of Australia" and draft == "" and not took_offer


def test_bare_follow_up_uses_the_previous_question_and_draft():
    messages = [{"role": "user", "content": "Explain VLANs briefly"},
                {"role": "assistant", "content": "A VLAN is a logical subnetwork.\n\n*answered by qwen on the Intel GPU*"},
                {"role": "user", "content": "ask Claude"}]
    question, draft, _ = mentor.mentor_question(messages, "ask Claude")
    assert question == "Explain VLANs briefly"
    assert draft == "A VLAN is a logical subnetwork."  # footers removed


def test_draft_with_sources_footer_is_never_sent():
    messages = [{"role": "user", "content": "What did I decide?"},
                {"role": "assistant", "content": "You chose X [1].\n\nSources:\n[1] notes/Decision.md"},
                {"role": "user", "content": "ask Claude"}]
    assert mentor.mentor_question(messages, "ask Claude")[1] == ""


def test_taking_aidens_offer_is_recognised():
    messages = [{"role": "user", "content": "What will EUR/USD be next year?"},
                {"role": "assistant", "content": f"I can't know.\n\n*{router.MENTOR_OFFER}*"},
                {"role": "user", "content": "ask Claude"}]
    assert mentor.mentor_question(messages, "ask Claude")[2] is True


# --- Draft privacy: judged by content, fails closed --------------------------------

def search_returning(*matches):
    return lambda text, limit=5: [{"path": p, "heading": "", "text": t, "score": s} for p, t, s in matches]


def test_draft_resembling_a_note_stays_local(monkeypatch):
    monkeypatch.setattr(mentor.vault, "search", search_returning(("pt/Verbs.md", "conhecer vs saber", 0.77)))
    safe, why, _ = mentor.draft_privacy("Conhecer is for people and places.")
    assert not safe and "resembles" in why


def test_general_draft_may_go(monkeypatch):
    monkeypatch.setattr(mentor.vault, "search", search_returning(("net/Notes.md", "unrelated", 0.55)))
    assert mentor.draft_privacy("A VLAN is a logical subnetwork.")[0] is True


def test_draft_sharing_wording_with_a_note_stays_local_even_with_a_low_score(monkeypatch):
    note = "we pinned postgres to seventeen because eighteen wants a different volume path"
    monkeypatch.setattr(mentor.vault, "search", search_returning(("ops/Postgres.md", note, 0.40)))
    safe, why, _ = mentor.draft_privacy(f"In short: {note}, so keep it.")
    assert not safe and "wording" in why


def test_draft_check_fails_closed_when_the_vault_is_unreachable(monkeypatch):
    def down(text, limit=5):
        raise requests.ConnectionError("qdrant down")
    monkeypatch.setattr(mentor.vault, "search", down)
    assert mentor.draft_privacy("anything")[0] is False


def test_text_resembling_aidens_own_notes_may_go_to_the_mentor(monkeypatch):
    """The user's decision: AIden's own notes describe AIden, not the user's life."""
    import mentor
    own = {"path": "HPC Engineering/InferenceDesign/AIden - Values.md", "score": 0.9, "text": "honesty matters", "heading": ""}
    private = {"path": "Clients/Volt/notes.md", "score": 0.9, "text": "client secret plan", "heading": ""}
    monkeypatch.setattr(mentor.vault, "search", lambda text, limit: [own])
    assert mentor.draft_privacy("I care about honesty")[0] is True
    monkeypatch.setattr(mentor.vault, "search", lambda text, limit: [own, private])
    assert mentor.draft_privacy("I care about honesty")[0] is False  # any other note still blocks


def test_own_note_names_with_commas_are_kept_whole():
    """Splitting on commas broke "AIden - Mind (Memory, Learning, Curiosity)" into pieces (seen live)."""
    import mentor
    assert "AIden - Mind (Memory, Learning, Curiosity)" in mentor.AIDEN_OWN_NOTES
    assert "AIden - NPU Adaptation & Next Steps" in mentor.AIDEN_OWN_NOTES
    assert not any(n.startswith("Learning") or n.endswith("(Memory") for n in mentor.AIDEN_OWN_NOTES)
