"""AIden's own tool protocol: any model asks with TOOL: lines, AIden runs the tools."""
import json

import pytest

import router
import toolbox


def sse(*parts):
    lines = [f"data: {json.dumps({'choices': [{'index': 0, 'delta': {'content': p}, 'finish_reason': None}]})}" for p in parts]
    return lines + [f"data: {json.dumps({'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}", "data: [DONE]"]


class Stream:
    encoding = None

    def __init__(self, lines):
        self.lines = lines

    def iter_lines(self, decode_unicode=True):
        yield from self.lines


class Reply:
    def __init__(self, content):
        self.content = content

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": self.content}}]}


TOOL_REQUEST = sse("TO", "OL: susp", "ends {}\nTOOL: uptime", " {}")
ANSWER = sse("You slept ", "3 times.\nConfidence: high")


@pytest.fixture(autouse=True)
def tools_answer(monkeypatch):
    monkeypatch.setattr(toolbox.terminal, "run", lambda command, /, **a: {"command": command, "ok": True, "output": 3})


@pytest.mark.parametrize("text, expected", [
    ("TOOL: suspends {}", [("suspends", "{}")]),
    ('TOOL: container_errors {"name": "ovms-gpu", "hours": 6}', [("container_errors", '{"name": "ovms-gpu", "hours": 6}')]),
    ("**TOOL:** uptime", [("uptime", "{}")]),
    ("`TOOL: memory {}`", [("memory", "{}")]),
    ("I'd check the tool: suspends", []),
])
def test_tool_lines_are_read_from_any_model(text, expected):
    assert [(c["name"], c["arguments"]) for c in toolbox.parse(text)] == expected


def test_an_answer_streams_through_untouched():
    text, replay = toolbox.peek(Stream(ANSWER))
    assert text is None and list(replay.iter_lines()) == ANSWER


def test_a_tool_request_split_across_chunks_is_read_whole():
    text, replay = toolbox.peek(Stream(TOOL_REQUEST))
    assert replay is None and [c["name"] for c in toolbox.parse(text)] == ["suspends", "uptime"]


def test_streamed_tool_round_then_answer():
    sent = []
    replies = iter([Stream(TOOL_REQUEST), Stream(ANSWER)])
    final, made = toolbox.converse(lambda m: sent.append(m) or next(replies),
                                   [{"role": "system", "content": "You are AIden."}, {"role": "user", "content": "q"}], True, True)
    assert list(final.iter_lines()) == ANSWER
    assert [(c["name"], c["ok"]) for c in made] == [("suspends", True), ("uptime", True)]
    first, second = sent
    assert "TOOL: <name>" in first[0]["content"] and first[0]["content"].startswith("You are AIden.")
    assert second[-2] == {"role": "assistant", "content": "TOOL: suspends {}\nTOOL: uptime {}"}
    assert second[-1]["role"] == "user" and "not from the user" in second[-1]["content"] and '"output": 3' in second[-1]["content"]


def test_non_streamed_tool_round():
    replies = iter([Reply("TOOL: uptime {}"), Reply("Up 13 h.")])
    final, made = toolbox.converse(lambda m: next(replies), [{"role": "user", "content": "q"}], False, True)
    assert final.json()["choices"][0]["message"]["content"] == "Up 13 h." and made[0]["name"] == "uptime"


def test_rounds_are_capped_and_the_last_request_has_no_tools():
    instructed = []

    def send(messages):
        has = "TOOL: <name>" in messages[0]["content"]
        instructed.append(has)
        return Stream(TOOL_REQUEST if has else ANSWER)

    final, made = toolbox.converse(send, [{"role": "system", "content": "s"}], True, True)
    assert instructed == [True] * toolbox.MAX_ROUNDS + [False] and list(final.iter_lines()) == ANSWER


def test_an_unreadable_tool_request_gets_a_plain_answer():
    replies = iter([Stream(sse("TOOL: please check everything")), Stream(ANSWER)])
    sent = []
    final, made = toolbox.converse(lambda m: sent.append(m) or next(replies), [{"role": "system", "content": "s"}], True, True)
    assert made == [] and list(final.iter_lines()) == ANSWER and "TOOL: <name>" not in sent[-1][0]["content"]


def test_models_not_offered_tools_get_one_plain_request(monkeypatch):
    monkeypatch.setattr(toolbox, "TOOL_BACKENDS", "ovms-gpu")
    assert toolbox.offered("ovms-gpu") and not toolbox.offered("ovms-npu")
    sent = []
    toolbox.converse(lambda m: sent.append(m) or Stream(ANSWER), [{"role": "system", "content": "s"}], True, False)
    assert len(sent) == 1 and sent[0][0]["content"] == "s"


def test_by_default_only_models_that_passed_the_test_get_tools(monkeypatch):
    assert toolbox.TOOL_BACKENDS == "auto"
    monkeypatch.setattr(toolbox_senses(), "tool_status", {"ovms-gpu": {"tools": True}, "ovms-npu": {"tools": False}})
    assert toolbox.offered("ovms-gpu") and not toolbox.offered("ovms-npu") and not toolbox.offered("ollama")


def toolbox_senses():
    import senses
    return senses


@pytest.mark.parametrize("name, arguments, expected", [
    ("rm_rf", "{}", "no such tool"), ("container", "not json", "bad arguments"), ("container", "[1]", "bad arguments")])
def test_bad_calls_are_answered_not_raised(name, arguments, expected):
    text, ok = toolbox.execute(name, arguments)
    assert not ok and expected in text


def test_tool_names_map_to_terminal_commands_and_extra_arguments_are_dropped(monkeypatch):
    seen = {}
    monkeypatch.setattr(toolbox.terminal, "run", lambda command, /, **a: seen.update(command=command, args=a) or {"ok": True})
    toolbox.execute("container_errors", json.dumps({"name": "ovms-gpu", "hours": 6, "cmd": "rm -rf /"}))
    assert seen == {"command": "container-errors", "args": {"name": "ovms-gpu", "hours": 6}}


def test_every_tool_has_a_command():
    for name in set(toolbox.TOOLS) - {"current_time", "model_health"}:
        assert name.replace("_", "-") in toolbox.terminal.COMMANDS


def test_footer_names_the_tools_used():
    footer = router.route_footer("ovms-gpu", "qwen", [], ["suspends", "suspends", "uptime"])
    assert footer.endswith("looked at: suspends, uptime*")


def test_invented_arguments_for_a_tool_without_any_are_ignored():
    # Phi on the NPU wrote Python-style arguments for a tool that takes none
    text, ok = toolbox.execute("suspends", "{u'reset_points': u'2023-04-03T11:15:00Z'}")
    assert ok and json.loads(text)["output"] == 3
