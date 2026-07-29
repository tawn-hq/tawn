"""Prompted tool calling — the fallback that lets any model use tools."""

from tawn.model.prompted import (
    inject_tools, parse_prompted_calls, prompted_system_block,
)
from tawn.model.types import Message, ToolCall, ToolSpec

SPEC = ToolSpec(
    name="recall",
    description="search memory",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
        "required": ["query"],
    },
)


# ── the instruction block ────────────────────────────────────────────────────

def test_the_block_names_every_tool_and_marks_optional_args():
    block = prompted_system_block([SPEC])
    assert "recall(" in block
    assert "query: string" in block      # required, no marker
    assert "top_k?: integer" in block    # optional, marked
    assert "search memory" in block
    assert "<tool_call>" in block


# ── parsing ──────────────────────────────────────────────────────────────────

def test_a_tagged_call_is_parsed_and_stripped_from_the_prose():
    text = 'Let me check.\n<tool_call>{"name": "recall", "arguments": {"query": "x"}}</tool_call>'
    calls, cleaned = parse_prompted_calls(text)
    assert [(c.name, c.arguments) for c in calls] == [("recall", {"query": "x"})]
    assert cleaned == "Let me check."


def test_several_calls_in_one_response():
    text = (
        '<tool_call>{"name": "a", "arguments": {}}</tool_call>'
        '<tool_call>{"name": "b", "arguments": {"n": 1}}</tool_call>'
    )
    calls, _ = parse_prompted_calls(text)
    assert [c.name for c in calls] == ["a", "b"]
    assert len({c.id for c in calls}) == 2  # ids must be distinct to pair results


def test_a_fenced_json_block_is_accepted_too():
    """Refusing a well-formed intent over its wrapper helps nobody."""
    text = '```json\n{"name": "recall", "arguments": {"query": "x"}}\n```'
    calls, _ = parse_prompted_calls(text)
    assert calls[0].name == "recall"


def test_the_args_key_is_accepted_as_well_as_arguments():
    text = '<tool_call>{"name": "recall", "args": {"query": "x"}}</tool_call>'
    assert parse_prompted_calls(text)[0][0].arguments == {"query": "x"}


def test_malformed_json_yields_no_call_rather_than_raising():
    calls, cleaned = parse_prompted_calls("<tool_call>{not json}</tool_call>")
    assert calls == []
    assert "not json" in cleaned  # left in the prose so nothing is silently eaten


def test_a_block_with_no_name_is_ignored():
    assert parse_prompted_calls('<tool_call>{"arguments": {}}</tool_call>')[0] == []


def test_non_dict_arguments_degrade_to_empty():
    text = '<tool_call>{"name": "recall", "arguments": "oops"}</tool_call>'
    assert parse_prompted_calls(text)[0][0].arguments == {}


def test_plain_prose_yields_nothing():
    calls, cleaned = parse_prompted_calls("Just an ordinary answer.")
    assert calls == []
    assert cleaned == "Just an ordinary answer."


def test_empty_input():
    assert parse_prompted_calls("") == ([], "")


# ── conversation rewriting ───────────────────────────────────────────────────

def test_instructions_are_appended_to_an_existing_system_turn():
    msgs = [Message(role="system", content="You are Tawn."),
            Message(role="user", content="hi")]
    out = inject_tools(msgs, [SPEC])
    assert out[0].role == "system"
    assert "You are Tawn." in out[0].content
    assert "<tool_call>" in out[0].content
    assert len(out) == 2


def test_a_system_turn_is_created_when_there_is_none():
    out = inject_tools([Message(role="user", content="hi")], [SPEC])
    assert out[0].role == "system"
    assert out[1].role == "user"


def test_tool_results_become_user_turns():
    """A model with no tools API also has no `tool` role."""
    msgs = [
        Message(role="user", content="q"),
        Message(role="assistant", content="",
                tool_calls=[ToolCall(id="c1", name="recall", arguments={"query": "x"})]),
        Message(role="tool", content="the answer", tool_call_id="c1"),
    ]
    out = inject_tools(msgs, [SPEC])
    roles = [m.role for m in out]
    assert "tool" not in roles
    result_turn = out[-1]
    assert result_turn.role == "user"
    assert "the answer" in result_turn.content


def test_a_previous_assistant_call_is_rendered_back_in_the_protocol():
    msgs = [
        Message(role="assistant", content="checking",
                tool_calls=[ToolCall(id="c1", name="recall", arguments={"query": "x"})]),
    ]
    out = inject_tools(msgs, [SPEC])
    rendered = out[-1].content
    assert "<tool_call>" in rendered
    assert '"name": "recall"' in rendered
    # It must round-trip: what we render, we must be able to parse.
    calls, _ = parse_prompted_calls(rendered)
    assert calls[0].name == "recall"
    assert calls[0].arguments == {"query": "x"}
