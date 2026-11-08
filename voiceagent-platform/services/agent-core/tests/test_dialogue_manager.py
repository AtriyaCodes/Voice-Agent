import asyncio
from typing import ClassVar

import pytest

from agent_core.dialogue_manager import DialogueManager
from agent_core.llm_client import LlmUnavailableError
from agent_core.memory import ConversationState, Turn


def _state():
    return ConversationState(channel_id="chan-1", tenant_id="acme", language="en-IN")


class ScriptedLlm:
    def __init__(self, events):
        self._events = events

    async def stream_response(self, messages, tools, system_prompt):
        for e in self._events:
            yield e


class RaisingLlm:
    async def stream_response(self, messages, tools, system_prompt):
        raise LlmUnavailableError("all providers down")
        yield {}  # pragma: no cover - makes this an async generator


class FakeTool:
    name = "capture_payment"
    description = "captures a payment"
    input_schema: ClassVar[dict] = {"type": "object", "properties": {}, "required": []}

    def __init__(self):
        self.calls = []

    async def invoke(self, *, channel_id, **kwargs):
        self.calls.append({"channel_id": channel_id, **kwargs})
        return "payment captured"


@pytest.mark.asyncio
async def test_handle_utterance_streams_text_and_records_turns():
    llm = ScriptedLlm([{"type": "text_delta", "text": "Hello"}, {"type": "text_delta", "text": " there"}])
    manager = DialogueManager(llm, tools=[], system_prompt_for_tenant=lambda t: "system prompt")
    state = _state()

    out = [chunk async for chunk in manager.handle_utterance(state, "hi")]

    assert out == ["Hello", " there"]
    assert state.turns[-2].role == "caller"
    assert state.turns[-1] == Turn(role="agent", text="Hello there")


@pytest.mark.asyncio
async def test_handle_utterance_binds_channel_id_and_merges_llm_tool_input():
    tool = FakeTool()
    llm = ScriptedLlm(
        [{"type": "tool_use", "tool_name": "capture_payment", "tool_input": {"amount_cents": 500, "currency": "INR"}}]
    )
    manager = DialogueManager(llm, tools=[tool], system_prompt_for_tenant=lambda t: "system prompt")
    state = _state()

    out = [chunk async for chunk in manager.handle_utterance(state, "pay my bill")]

    assert out == ["payment captured"]
    assert tool.calls == [{"channel_id": "chan-1", "amount_cents": 500, "currency": "INR"}]


@pytest.mark.asyncio
async def test_handle_utterance_stops_immediately_on_barge_in_cancellation():
    llm = ScriptedLlm([{"type": "text_delta", "text": "part one"}, {"type": "text_delta", "text": "part two"}])
    manager = DialogueManager(llm, tools=[], system_prompt_for_tenant=lambda t: "system prompt")
    state = _state()

    cancellation_token = asyncio.Event()
    cancellation_token.set()  # already cancelled before the first event is even checked

    out = [chunk async for chunk in manager.handle_utterance(state, "hi", cancellation_token)]

    assert out == []


@pytest.mark.asyncio
async def test_handle_utterance_degrades_gracefully_when_llm_is_unavailable():
    events_emitted = []

    async def emit(event):
        events_emitted.append(event)

    manager = DialogueManager(
        RaisingLlm(), tools=[], system_prompt_for_tenant=lambda t: "system prompt", emit_call_event=emit
    )
    state = _state()

    out = [chunk async for chunk in manager.handle_utterance(state, "hi")]

    assert len(out) == 1
    assert "trouble connecting" in out[0]
    assert state.turns[-1].role == "agent"
    assert events_emitted[0]["eventType"] == "degraded"


@pytest.mark.asyncio
async def test_start_call_emits_disclosure_for_banking_tenants_only():
    events_emitted = []

    async def emit(event):
        events_emitted.append(event)

    manager = DialogueManager(
        ScriptedLlm([]), tools=[], system_prompt_for_tenant=lambda t: "system prompt", emit_call_event=emit
    )

    banking_state = _state()
    disclosure = [chunk async for chunk in manager.start_call(banking_state, "banking")]
    assert len(disclosure) == 1
    assert "automated assistant" in disclosure[0]
    assert banking_state.turns[0].role == "agent"
    assert events_emitted[0]["eventType"] == "disclosure_acknowledged"

    standard_state = _state()
    events_emitted.clear()
    no_disclosure = [chunk async for chunk in manager.start_call(standard_state, "standard")]
    assert no_disclosure == []
    assert standard_state.turns == []
    assert events_emitted == []
