from types import SimpleNamespace

import pytest

from agent_core.llm_client import (
    CircuitBreaker,
    CircuitBreakerConfig,
    LlmClient,
    LlmUnavailableError,
    ResilientLlmClient,
)


def _delta_event(index, delta_type, **kwargs):
    return SimpleNamespace(type="content_block_delta", index=index, delta=SimpleNamespace(type=delta_type, **kwargs))


def _block_start(index, block_type, **kwargs):
    return SimpleNamespace(
        type="content_block_start", index=index, content_block=SimpleNamespace(type=block_type, **kwargs)
    )


def _block_stop(index):
    return SimpleNamespace(type="content_block_stop", index=index)


class FakeAnthropicStream:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for e in self._events:
            yield e


class FakeAnthropicMessages:
    def __init__(self, events):
        self._events = events

    def stream(self, **kwargs):
        return FakeAnthropicStream(self._events)


class FakeAnthropicClient:
    def __init__(self, events):
        self.messages = FakeAnthropicMessages(events)


@pytest.mark.asyncio
async def test_llm_client_maps_text_deltas():
    events = [
        _block_start(0, "text"),
        _delta_event(0, "text_delta", text="Hello"),
        _delta_event(0, "text_delta", text=" there"),
        _block_stop(0),
    ]
    client = LlmClient(api_key="unused", model="claude-sonnet-5", client=FakeAnthropicClient(events))

    out = [e async for e in client.stream_response(messages=[], tools=[], system_prompt="")]

    assert out == [
        {"type": "text_delta", "text": "Hello"},
        {"type": "text_delta", "text": " there"},
    ]


@pytest.mark.asyncio
async def test_llm_client_accumulates_tool_use_json_deltas():
    events = [
        _block_start(0, "tool_use", name="capture_payment"),
        _delta_event(0, "input_json_delta", partial_json='{"amount_c'),
        _delta_event(0, "input_json_delta", partial_json='ents": 500, "currency": "INR"}'),
        _block_stop(0),
    ]
    client = LlmClient(api_key="unused", model="claude-sonnet-5", client=FakeAnthropicClient(events))

    out = [e async for e in client.stream_response(messages=[], tools=[], system_prompt="")]

    assert out == [
        {"type": "tool_use", "tool_name": "capture_payment", "tool_input": {"amount_cents": 500, "currency": "INR"}}
    ]


def test_circuit_breaker_opens_after_threshold_and_half_opens_after_cooldown():
    now = [0.0]
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=10), clock=lambda: now[0])

    assert breaker.is_call_permitted is True
    breaker.on_failure()
    assert breaker.state == "CLOSED"
    breaker.on_failure()
    assert breaker.state == "OPEN"
    assert breaker.is_call_permitted is False

    now[0] = 11.0
    assert breaker.is_call_permitted is True
    assert breaker.state == "HALF_OPEN"

    breaker.on_success()
    assert breaker.state == "CLOSED"


def test_circuit_breaker_reopens_immediately_on_half_open_failure():
    now = [0.0]
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=5), clock=lambda: now[0])
    breaker.on_failure()
    assert breaker.state == "OPEN"

    now[0] = 6.0
    assert breaker.is_call_permitted is True  # half-open trial
    breaker.on_failure()
    assert breaker.state == "OPEN"


class ScriptedProvider:
    def __init__(self, events=None, error=None):
        self._events = events or []
        self._error = error

    async def stream_response(self, messages, tools, system_prompt):
        if self._error is not None:
            raise self._error
        for e in self._events:
            yield e


@pytest.mark.asyncio
async def test_resilient_client_falls_back_to_second_provider_on_first_failure():
    primary = ScriptedProvider(error=RuntimeError("timeout"))
    fallback = ScriptedProvider(events=[{"type": "text_delta", "text": "ok"}])
    client = ResilientLlmClient([("primary", primary), ("fallback", fallback)])

    out = [e async for e in client.stream_response(messages=[], tools=[], system_prompt="")]

    assert out == [{"type": "text_delta", "text": "ok"}]


@pytest.mark.asyncio
async def test_resilient_client_raises_when_all_providers_fail():
    primary = ScriptedProvider(error=RuntimeError("down"))
    secondary = ScriptedProvider(error=RuntimeError("also down"))
    client = ResilientLlmClient([("primary", primary), ("secondary", secondary)])

    with pytest.raises(LlmUnavailableError):
        async for _ in client.stream_response(messages=[], tools=[], system_prompt=""):
            pass


@pytest.mark.asyncio
async def test_resilient_client_fires_filler_callback_on_slow_first_token():
    now = [0.0]

    async def slow_stream(messages, tools, system_prompt):
        now[0] += 1.0  # simulate elapsed time before the first token
        yield {"type": "text_delta", "text": "hi"}

    provider = SimpleNamespace(stream_response=slow_stream)
    filler_calls = []

    client = ResilientLlmClient(
        [("primary", provider)],
        slow_ttft_seconds=0.3,
        on_slow_ttft=lambda: filler_calls.append(1),
        clock=lambda: now[0],
    )

    out = [e async for e in client.stream_response(messages=[], tools=[], system_prompt="")]

    assert out == [{"type": "text_delta", "text": "hi"}]
    assert filler_calls == [1]
