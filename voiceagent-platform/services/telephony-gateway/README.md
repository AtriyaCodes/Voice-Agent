# telephony-gateway

Owns SIP signaling (via Asterisk ARI or FreeSWITCH ESL) and RTP media
bridging for VoiceAgent calls. This service has no knowledge of dialogue or
LLM logic; it forwards raw audio to voice-pipeline and executes call
control instructions (answer, hangup, transfer) coming from agent-core
via orchestration-api.

## Run locally

```bash
pip install -e ".[dev]"
python -m telephony_gateway.main
```

## Test

```bash
python -m pytest
```
