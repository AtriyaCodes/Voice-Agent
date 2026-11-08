"""Entry point for the telephony-gateway service."""

from __future__ import annotations

import asyncio
import os

import structlog
from dotenv import load_dotenv

from telephony_gateway.sip_handler import SipHandler

logger = structlog.get_logger(__name__)


async def on_call_started(context) -> None:
    logger.info("dispatching_call_to_agent_core", tenant_id=context.tenant_id)


async def on_call_ended(channel_id: str) -> None:
    logger.info("cleaning_up_call", channel_id=channel_id)


async def main() -> None:
    load_dotenv()
    ari_url = os.environ.get("ASTERISK_ARI_URL", "http://localhost:8088/ari")
    logger.info("starting_telephony_gateway", ari_url=ari_url)

    # ari_client construction is deployment specific (Asterisk ARI vs
    # FreeSWITCH ESL); see docs/adr/0002-sip-telephony-stack-choice.md
    ari_client = None
    handler = SipHandler(ari_client, on_call_started, on_call_ended)  # noqa: F841

    # Event loop subscribing to ARI/ESL events would be started here.
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
