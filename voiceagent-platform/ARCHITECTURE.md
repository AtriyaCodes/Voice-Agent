# VoiceAgent Platform Architecture

## Call flow, end to end

1. **Inbound call arrives** at the telephony gateway over SIP trunking (carrier or the customer's existing PBX/contact center platform).
2. **telephony-gateway** answers the call, establishes the RTP media stream, and opens a bidirectional audio stream to **voice-pipeline** over gRPC.
3. **voice-pipeline** runs voice activity detection on the inbound audio and streams speech to the STT engine as soon as a speech segment is detected, rather than waiting for full utterance boundaries. Partial transcripts are pushed to **agent-core** as they become available.
4. **agent-core** maintains the dialogue state for the call, decides when it has enough of the utterance to act, and either continues listening, calls a tool, or generates a response. Tool calls (for example, a payment capture) are routed through a separate, isolated path (see `compliance/pci/`), never through the general LLM context.
5. The response text streams back through **voice-pipeline**'s TTS engine, which begins producing audio before the full response text is generated, and that audio is streamed back to **telephony-gateway** for playback on the call.
6. **orchestration-api** sits above all of this. It authenticates the inbound call to a tenant, resolves that tenant's configuration (voice, language, prompt set, allowed tools, compliance mode), and coordinates session lifecycle and call metadata across the other services. It is what the admin dashboard and any customer facing integration talk to.

## Latency budget

The sub-500ms target is a budget across the whole loop above, not a property of any one component:

| Stage | Budget |
|---|---|
| VAD + partial STT | under 150ms |
| Dialogue decision in agent-core | under 120ms |
| LLM time to first token | under 150ms |
| TTS time to first audio byte | under 80ms |

Each service exports these stage latencies as metrics so a regression is traceable to a specific stage rather than showing up only as an aggregate number.

## Multi-tenancy

A single VoiceAgent Platform deployment can host multiple white-labeled agents. Tenant identity is resolved at the orchestration-api layer at call setup and threaded through every downstream service call as a tenant context, which drives voice selection, language, prompt/tooling configuration, and, in banking deployments, full front-to-back data segregation between tenants.

## Compliance boundary

Payment capture is deliberately kept out of the general conversation and LLM context. See `compliance/pci/README.md` for the isolation design. This is a hard boundary at the service level, not a prompt-level instruction.

## Deployment model

VoiceAgent Platform supports both on-premise/air-gapped deployment and cloud deployment. See `infra/` for docker-compose (local/dev) and Kubernetes manifests (staging/production and on-prem clusters).
