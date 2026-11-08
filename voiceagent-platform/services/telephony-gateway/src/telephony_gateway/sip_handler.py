"""SIP call control via Asterisk ARI (Asterisk REST Interface).

This module owns the signaling side of a call: answering, hanging up,
transferring, and reacting to ARI events such as StasisStart and
ChannelHangupRequest. It does not touch media directly; media is handled
by rtp_stream.py once a channel is bridged into an external media path.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CallContext:
    """Everything downstream services need to know about a single call."""

    channel_id: str
    tenant_id: str
    caller_number: str
    called_number: str
    sip_trunk: str


class SipHandler:
    """Thin wrapper around the Asterisk ARI client for call lifecycle events."""

    def __init__(self, ari_client, on_call_started, on_call_ended):
        self._ari = ari_client
        self._on_call_started = on_call_started
        self._on_call_ended = on_call_ended

    async def handle_stasis_start(self, event: dict) -> None:
        """Called when Asterisk hands a new channel into our Stasis app."""
        channel = event["channel"]
        context = CallContext(
            channel_id=channel["id"],
            tenant_id=self._resolve_tenant(event),
            caller_number=channel["caller"]["number"],
            called_number=channel["dialplan"]["exten"],
            sip_trunk=channel.get("channelvars", {}).get("SIP_TRUNK", "default"),
        )
        logger.info("call_started", channel_id=context.channel_id, tenant_id=context.tenant_id)
        await self._ari.answer(context.channel_id)
        await self._on_call_started(context)

    async def handle_hangup(self, event: dict) -> None:
        channel_id = event["channel"]["id"]
        logger.info("call_ended", channel_id=channel_id)
        await self._on_call_ended(channel_id)

    def _resolve_tenant(self, event: dict) -> str:
        """Tenant resolution from DID, SIP trunk header, or dialplan variable.

        This should stay a thin lookup. The source of truth for tenant
        configuration lives in orchestration-api, not here.
        """
        channel = event["channel"]
        return channel.get("channelvars", {}).get("TENANT_ID", "unassigned")
