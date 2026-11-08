import pytest

from telephony_gateway.sip_handler import SipHandler


class FakeAriClient:
    def __init__(self):
        self.answered = []

    async def answer(self, channel_id: str) -> None:
        self.answered.append(channel_id)


@pytest.mark.asyncio
async def test_handle_stasis_start_answers_and_dispatches():
    ari = FakeAriClient()
    started_contexts = []

    async def on_started(context):
        started_contexts.append(context)

    async def on_ended(channel_id):
        pass

    handler = SipHandler(ari, on_started, on_ended)
    event = {
        "channel": {
            "id": "chan-1",
            "caller": {"number": "+911234567890"},
            "dialplan": {"exten": "1000"},
            "channelvars": {"TENANT_ID": "acme", "SIP_TRUNK": "contosoip"},
        }
    }

    await handler.handle_stasis_start(event)

    assert ari.answered == ["chan-1"]
    assert started_contexts[0].tenant_id == "acme"
    assert started_contexts[0].sip_trunk == "contosoip"
