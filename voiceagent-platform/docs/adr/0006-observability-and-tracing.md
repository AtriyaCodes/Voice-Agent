# 6. Observability and tracing strategy

## Status
Accepted

## Context
ARCHITECTURE.md commits to a per-stage latency budget (VAD+partial STT
<150ms, dialogue decision <120ms, LLM TTFT <150ms, TTS first byte <80ms)
"so a regression is traceable to a specific stage rather than showing up
only as an aggregate number." Nothing enforced that claim: there was no
trace correlation across services, and the CI job meant to catch a
regression was a literal `echo "placeholder"`.

## Decision
- A `trace_id` is generated once per call, at telephony-gateway (call
  start), and threaded unchanged through every downstream hop:
  `shared/proto/voice_session.proto`'s `AudioFrame` and `PipelineEvent`
  both carry it, so voice-pipeline and agent-core can tag their own spans
  with the same id a trace backend (Jaeger/Tempo/etc.) can join into one
  per-call timeline instead of four separate service logs.
- `scripts/latency_benchmark.py` replaces the CI placeholder. It is
  intentionally scoped to what CI can check honestly without network
  access to a real STT/LLM/TTS provider: VAD+AEC processing cost is
  measured for real against its share of the budget, and the platform's
  own dispatch overhead around the LLM call is measured against a much
  tighter internal budget using a zero-latency fake provider — catching a
  regression in *our* code (e.g. an accidentally blocking call added to
  the hot path) even though the actual provider round-trip time is out of
  scope for unit CI.
- Real end-to-end LLM-TTFT/TTS-first-byte budget verification belongs in
  a staging synthetic-call test against live providers, not in this CI
  job — that's a deliberate scope boundary, not a gap being glossed over.

## Consequences
- Per-stage OpenTelemetry span instrumentation inside each service (VAD
  span, STT span, LLM-TTFT span, TTS span) is the next concrete step this
  ADR sets up for but does not itself implement — the trace_id plumbing
  is the prerequisite; wiring an OTel SDK and exporter per service is
  tracked as follow-up work, not bundled into this pass to keep the proto
  change reviewable on its own.
- `latency_benchmark.py` running in CI means a PR that regresses VAD/AEC
  processing cost or dialogue dispatch overhead fails the build
  immediately, rather than only surfacing once someone notices call
  quality degrading in production.
