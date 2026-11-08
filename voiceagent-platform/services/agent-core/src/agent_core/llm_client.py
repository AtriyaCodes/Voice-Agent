"""LLM provider wrapper used for dialogue generation.

Two layers here, deliberately kept separate:

- `LlmClient`: talks to a real provider (Anthropic) and maps its
  streaming protocol to the plain `text_delta` / `tool_use` event shape
  dialogue_manager.py already expects.
- `ResilientLlmClient`: the thing dialogue_manager actually holds. It
  wraps an ordered list of providers with a circuit breaker per provider
  and a "thinking filler" callback — a stalled or erroring LLM call on a
  live phone call is not an exception to log and move on from, it's dead
  air the caller is sitting through, so this is where that gets handled
  (fall back to the next provider; if all of them are down, surface a
  typed error dialogue_manager turns into a degraded response rather than
  a raised exception that kills the call).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


class LlmProvider(Protocol):
    async def stream_response(
        self, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> AsyncIterator[dict]: ...


class LlmClient:
    """Anthropic-backed implementation of LlmProvider.

    Kept separate from dialogue_manager so prompt construction and tool
    schema wiring stay in one place, and so the provider can be swapped
    (or run against an on-prem model for air-gapped deployments) without
    touching dialogue logic — dialogue_manager only ever depends on the
    LlmProvider protocol, never on this class directly.
    """

    def __init__(self, api_key: str, model: str, *, max_tokens: int = 1024, client=None):
        self._model = model
        self._max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def stream_response(
        self, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> AsyncIterator[dict]:
        pending_tool_use: dict[int, dict] = {}

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    pending_tool_use[event.index] = {"name": event.content_block.name, "json": ""}

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "text_delta", "text": event.delta.text}
                    elif event.delta.type == "input_json_delta":
                        pending_tool_use[event.index]["json"] += event.delta.partial_json

                elif event.type == "content_block_stop" and event.index in pending_tool_use:
                    block = pending_tool_use.pop(event.index)
                    import json

                    tool_input = json.loads(block["json"]) if block["json"] else {}
                    yield {"type": "tool_use", "tool_name": block["name"], "tool_input": tool_input}


class LlmUnavailableError(Exception):
    """Raised when every configured provider is unavailable (circuit open
    or the call itself failed) — dialogue_manager catches this and
    degrades the call instead of letting the exception kill it."""


class _BreakerState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0


class CircuitBreaker:
    """Standard consecutive-failure circuit breaker.

    Without this, a failing provider gets retried on every single turn of
    every active call, each retry adding latency and burning API quota
    while the provider is down — a retry storm on top of an outage. Once
    open, calls fail fast until the cooldown elapses, then one trial call
    is allowed through (half-open) to test recovery.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None, clock=time.monotonic):
        self._config = config or CircuitBreakerConfig()
        self._clock = clock
        self._state = _BreakerState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_call_permitted(self) -> bool:
        if self._state == _BreakerState.OPEN:
            assert self._opened_at is not None
            if self._clock() - self._opened_at >= self._config.cooldown_seconds:
                self._state = _BreakerState.HALF_OPEN
                return True
            return False
        return True

    def on_success(self) -> None:
        self._state = _BreakerState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None

    def on_failure(self) -> None:
        self._consecutive_failures += 1
        if self._state == _BreakerState.HALF_OPEN or self._consecutive_failures >= self._config.failure_threshold:
            self._state = _BreakerState.OPEN
            self._opened_at = self._clock()

    @property
    def state(self) -> str:
        return self._state.name


@dataclass
class _ProviderSlot:
    name: str
    provider: LlmProvider
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)


class ResilientLlmClient:
    """What dialogue_manager actually holds: an ordered fallback chain of
    providers, each behind its own circuit breaker, plus a filler-phrase
    hook fired when the first token is slow to arrive."""

    def __init__(
        self,
        providers: list[tuple[str, LlmProvider]],
        *,
        breaker_config: CircuitBreakerConfig | None = None,
        slow_ttft_seconds: float = 0.3,
        on_slow_ttft=None,
        clock=time.monotonic,
    ):
        if not providers:
            raise ValueError("ResilientLlmClient needs at least one provider")
        self._slots = [_ProviderSlot(name, provider, CircuitBreaker(breaker_config)) for name, provider in providers]
        self._slow_ttft_seconds = slow_ttft_seconds
        self._on_slow_ttft = on_slow_ttft
        self._clock = clock

    async def stream_response(
        self, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> AsyncIterator[dict]:
        last_error: Exception | None = None

        for slot in self._slots:
            if not slot.breaker.is_call_permitted:
                logger.info("llm_provider_breaker_open_skipping", provider=slot.name)
                continue

            try:
                async for event in self._stream_with_filler(slot, messages, tools, system_prompt):
                    yield event
                slot.breaker.on_success()
                return
            except Exception as exc:  # noqa: BLE001 - deliberately broad: any provider failure falls back
                slot.breaker.on_failure()
                last_error = exc
                logger.warning(
                    "llm_provider_failed_falling_back",
                    provider=slot.name,
                    breaker_state=slot.breaker.state,
                    error=str(exc),
                )
                continue

        raise LlmUnavailableError("all configured LLM providers are unavailable") from last_error

    async def _stream_with_filler(
        self, slot: _ProviderSlot, messages: list[dict], tools: list[dict], system_prompt: str
    ) -> AsyncIterator[dict]:
        start = self._clock()
        first_event_seen = False

        async for event in slot.provider.stream_response(messages, tools, system_prompt):
            if not first_event_seen:
                first_event_seen = True
                elapsed = self._clock() - start
                if elapsed > self._slow_ttft_seconds and self._on_slow_ttft is not None:
                    await _maybe_await(self._on_slow_ttft())
            yield event


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    return value
