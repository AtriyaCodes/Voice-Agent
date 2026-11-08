# orchestration-api

Session orchestration, tenant management, and the external REST API for
VoiceAgent. This service resolves tenant identity and configuration at call
setup and coordinates session lifecycle across telephony-gateway,
voice-pipeline, and agent-core. It holds no audio or dialogue logic
itself.

## Run locally

```bash
npm install
npm run dev
```

## Test

```bash
npm test
```
