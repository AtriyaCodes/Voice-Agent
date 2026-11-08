"""Per-call conversation state.

Backed by Redis so a call can survive a service restart mid-conversation
without losing context, and so orchestration-api can read call state for
monitoring without owning dialogue logic itself. `save`/`load` take any
object exposing the same minimal async `get`/`set` surface as
`redis.asyncio.Redis` (that's what's injected in production, and what
`tests/test_memory.py` fakes for unit tests without a live Redis).

`turns` growing without bound is not a cosmetic problem here: agent-core
sends the full history to the LLM on every turn
(`as_llm_messages()`), and the platform's own latency budget
(ARCHITECTURE.md) gives the LLM stage 150ms time-to-first-token. A call
that runs long (support/collections calls routinely run 5-10+ minutes)
will grow past what fits in that budget if nothing trims it —
`summarize_if_over_budget` is that trim, collapsing older turns into one
summary turn via the same LLM client rather than growing forever.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol


class AsyncKeyValueStore(Protocol):
    """The minimal slice of the redis.asyncio.Redis interface this module
    needs — kept narrow so tests can fake it trivially."""

    async def get(self, key: str) -> bytes | str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> object: ...


@dataclass
class Turn:
    role: str  # "caller" or "agent"
    text: str


@dataclass
class ConversationState:
    channel_id: str
    tenant_id: str
    language: str
    turns: list[Turn] = field(default_factory=list)

    def add_turn(self, role: str, text: str) -> None:
        self.turns.append(Turn(role=role, text=text))

    def as_llm_messages(self) -> list[dict]:
        role_map = {"caller": "user", "agent": "assistant"}
        return [{"role": role_map[t.role], "content": t.text} for t in self.turns]

    def approx_token_count(self) -> int:
        """Cheap chars/4 estimate — good enough for a trim threshold,
        not meant to match a tokenizer exactly."""
        return sum(len(t.text) for t in self.turns) // 4

    async def summarize_if_over_budget(
        self,
        summarize: Callable[[list[Turn]], Awaitable[str]],
        *,
        budget_tokens: int = 1500,
        keep_recent_turns: int = 6,
    ) -> bool:
        """Collapses older turns into one summary turn if the conversation
        has grown past budget_tokens. Returns True if it did."""
        if self.approx_token_count() <= budget_tokens or len(self.turns) <= keep_recent_turns:
            return False

        turns_to_summarize = self.turns[:-keep_recent_turns]
        recent_turns = self.turns[-keep_recent_turns:]
        summary_text = await summarize(turns_to_summarize)

        self.turns = [
            Turn(role="agent", text=f"[Summary of earlier conversation: {summary_text}]"),
            *recent_turns,
        ]
        return True

    def _redis_key(self) -> str:
        return conversation_redis_key(self.channel_id)

    async def save(self, store: AsyncKeyValueStore, *, ttl_seconds: int = 4 * 3600) -> None:
        payload = json.dumps(
            {
                "channel_id": self.channel_id,
                "tenant_id": self.tenant_id,
                "language": self.language,
                "turns": [{"role": t.role, "text": t.text} for t in self.turns],
            }
        )
        await store.set(self._redis_key(), payload, ex=ttl_seconds)

    @classmethod
    async def load(cls, store: AsyncKeyValueStore, channel_id: str) -> ConversationState | None:
        raw = await store.get(conversation_redis_key(channel_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return cls(
            channel_id=data["channel_id"],
            tenant_id=data["tenant_id"],
            language=data["language"],
            turns=[Turn(role=t["role"], text=t["text"]) for t in data["turns"]],
        )


def conversation_redis_key(channel_id: str) -> str:
    return f"voiceagent:conversation:{channel_id}"
