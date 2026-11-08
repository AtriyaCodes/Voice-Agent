import pytest

from agent_core.memory import ConversationState, Turn, conversation_redis_key


def test_conversation_state_round_trips_to_llm_messages():
    state = ConversationState(channel_id="chan-1", tenant_id="acme", language="en-IN")
    state.add_turn("caller", "I want to check my invoice status")
    state.add_turn("agent", "Sure, can you share your invoice number?")

    messages = state.as_llm_messages()

    assert messages == [
        {"role": "user", "content": "I want to check my invoice status"},
        {"role": "assistant", "content": "Sure, can you share your invoice number?"},
    ]


class FakeRedis:
    """Fakes just enough of redis.asyncio.Redis for save/load round trips."""

    def __init__(self):
        self._data: dict[str, str] = {}

    async def get(self, key: str):
        value = self._data.get(key)
        return value.encode("utf-8") if value is not None else None

    async def set(self, key: str, value: str, ex: int | None = None):
        self._data[key] = value
        return True


@pytest.mark.asyncio
async def test_save_and_load_round_trip_against_a_fake_redis():
    store = FakeRedis()
    state = ConversationState(channel_id="chan-1", tenant_id="acme", language="en-IN")
    state.add_turn("caller", "What's my balance?")
    state.add_turn("agent", "Your balance is 4,200 rupees.")

    await state.save(store)
    loaded = await ConversationState.load(store, "chan-1")

    assert loaded is not None
    assert loaded.channel_id == "chan-1"
    assert loaded.tenant_id == "acme"
    assert loaded.language == "en-IN"
    assert loaded.turns == state.turns


@pytest.mark.asyncio
async def test_load_returns_none_for_a_call_with_no_saved_state():
    store = FakeRedis()
    assert await ConversationState.load(store, "never-seen-channel") is None


def test_conversation_redis_key_is_namespaced_per_channel():
    assert conversation_redis_key("chan-1") == "voiceagent:conversation:chan-1"


@pytest.mark.asyncio
async def test_summarize_if_over_budget_collapses_old_turns_and_keeps_recent_ones():
    state = ConversationState(channel_id="chan-1", tenant_id="acme", language="en-IN")
    # Build a long-enough history to exceed a small test budget.
    for i in range(20):
        state.add_turn("caller", f"This is turn {i} with some padding text to add length. " * 3)
        state.add_turn("agent", f"Acknowledged turn {i}, here is a longer reply as well. " * 3)

    async def fake_summarize(turns_to_summarize: list[Turn]) -> str:
        return f"caller discussed {len(turns_to_summarize)} earlier turns"

    changed = await state.summarize_if_over_budget(fake_summarize, budget_tokens=50, keep_recent_turns=4)

    assert changed is True
    assert len(state.turns) == 5  # 1 summary turn + 4 kept recent turns
    assert "Summary of earlier conversation" in state.turns[0].text
    assert state.turns[-1].text == "Acknowledged turn 19, here is a longer reply as well. " * 3


@pytest.mark.asyncio
async def test_summarize_if_over_budget_is_a_noop_when_under_budget():
    state = ConversationState(channel_id="chan-1", tenant_id="acme", language="en-IN")
    state.add_turn("caller", "Hi")
    state.add_turn("agent", "Hello, how can I help?")

    async def fail_if_called(turns_to_summarize: list[Turn]) -> str:
        raise AssertionError("should not summarize a short conversation")

    changed = await state.summarize_if_over_budget(fail_if_called, budget_tokens=1500, keep_recent_turns=6)

    assert changed is False
    assert len(state.turns) == 2
