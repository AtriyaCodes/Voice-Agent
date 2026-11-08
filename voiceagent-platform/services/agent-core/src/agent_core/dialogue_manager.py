"""Owns the decision loop for a single call: given a finalized utterance,
decide what the agent says or does next.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC

import structlog

from agent_core.compliance import CompliancePolicy
from agent_core.llm_client import LlmProvider, LlmUnavailableError
from agent_core.memory import ConversationState

logger = structlog.get_logger(__name__)

_DEGRADED_RESPONSE_TEXT = (
    "I'm having trouble connecting right now. Let me get you to someone who can help."
)


class DialogueManager:
    def __init__(
        self,
        llm_client: LlmProvider,
        tools: list,
        system_prompt_for_tenant: Callable[[str], str],
        *,
        compliance_policy: CompliancePolicy | None = None,
        emit_call_event: Callable[[dict], Awaitable[None]] | None = None,
    ):
        self._llm = llm_client
        self._tools = tools
        self._system_prompt_for_tenant = system_prompt_for_tenant
        self._compliance = compliance_policy or CompliancePolicy()
        self._emit_call_event = emit_call_event

    async def start_call(self, state: ConversationState, compliance_mode: str) -> AsyncIterator[str]:
        """Called once, before the first caller utterance is handled.
        Yields the regulatory disclosure turn for regulated tenants (see
        compliance.py) and records it in call state and the event stream;
        yields nothing for tenants that don't require it."""
        if not self._compliance.requires_disclosure(compliance_mode):
            return

        disclosure_text = self._compliance.disclosure_text(state.language)
        state.add_turn("agent", disclosure_text)
        yield disclosure_text

        if self._emit_call_event is not None:
            event = self._compliance.build_disclosure_event(
                channel_id=state.channel_id, tenant_id=state.tenant_id
            )
            await self._emit_call_event(
                {
                    "channelId": event.channel_id,
                    "tenantId": event.tenant_id,
                    "eventType": "disclosure_acknowledged",
                    "timestamp": event.timestamp,
                }
            )

    async def handle_utterance(
        self,
        state: ConversationState,
        utterance_text: str,
        cancellation_token: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        state.add_turn("caller", utterance_text)
        system_prompt = self._system_prompt_for_tenant(state.tenant_id)

        response_text_parts: list[str] = []
        try:
            async for event in self._llm.stream_response(
                messages=state.as_llm_messages(),
                tools=self._tool_schemas(),
                system_prompt=system_prompt,
            ):
                if cancellation_token is not None and cancellation_token.is_set():
                    logger.info("llm_stream_cancelled_on_barge_in", channel_id=state.channel_id)
                    return

                if event["type"] == "text_delta":
                    response_text_parts.append(event["text"])
                    yield event["text"]
                elif event["type"] == "tool_use":
                    result = await self._invoke_tool(state, event["tool_name"], event["tool_input"])
                    logger.info("tool_invoked", tool=event["tool_name"], channel_id=state.channel_id)
                    yield result
        except LlmUnavailableError:
            logger.error("llm_unavailable_degrading_call", channel_id=state.channel_id)
            response_text_parts = [_DEGRADED_RESPONSE_TEXT]
            yield _DEGRADED_RESPONSE_TEXT
            if self._emit_call_event is not None:
                await self._emit_call_event(
                    {
                        "channelId": state.channel_id,
                        "tenantId": state.tenant_id,
                        "eventType": "degraded",
                        "timestamp": _utc_now_iso(),
                    }
                )

        state.add_turn("agent", "".join(response_text_parts))

    def _tool_schemas(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools
        ]

    async def _invoke_tool(self, state: ConversationState, tool_name: str, tool_input: dict) -> str:
        tool = next((t for t in self._tools if t.name == tool_name), None)
        if tool is None:
            logger.warning("unknown_tool_requested", tool_name=tool_name)
            return ""
        # channel_id is call context, not something the model should be
        # trusted (or even able) to supply — it's bound here, not taken
        # from the LLM's tool_use input.
        result = await tool.invoke(channel_id=state.channel_id, **tool_input)
        return str(result)


def _utc_now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()
