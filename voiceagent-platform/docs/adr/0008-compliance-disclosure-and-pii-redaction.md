# 8. Compliance disclosure, PII redaction, and payment-tool idempotency

## Status
Accepted

## Context
Three related gaps surfaced from looking at this platform the way someone
who has actually run a regulated voice deployment would:

1. RBI's guidance on AI/voice bots in banking, and India's DPDP Act 2023
   more broadly, require an automated calling assistant to disclose that
   the call may be recorded and that the caller is speaking with an
   automated system — as a logged, timestamped, auditable event, not a
   line in a policy document. Nothing produced that disclosure or that
   record.
2. `compliance/pci/README.md`'s isolation boundary is scoped specifically
   to cardholder data. It says nothing about account numbers, OTPs, or
   similar sensitive-but-not-card data a caller says out loud on an
   ordinary banking call, which can still end up in `CallEvent.metadata`
   on its way to the analytics/QA store — a wider audience than the call
   itself.
3. `PaymentCaptureTool.invoke` had no retry protection at all. A network
   timeout talking to the PCI-scoped payment service doesn't mean the
   charge didn't happen — it means agent-core doesn't know. Retrying
   blindly risks a double charge.

## Decision
- `agent_core/compliance.py`'s `CompliancePolicy` gates a disclosure turn
  on the tenant's `complianceMode` (`banking` requires it; `standard`
  does not) and produces both the spoken disclosure text (language-aware:
  `en-IN`/`hi-IN` today, extendable) and a `disclosure_acknowledged`
  `CallEvent`. `DialogueManager.start_call` is the integration point,
  called once before the first caller utterance — this is a greeting-time
  concern, not something triggered by what the caller says.
- `agent_core/redaction.py` applies pattern-based redaction (OTP-shaped
  4-8 digit runs, longer account-number-shaped digit runs) to
  `CallEvent.metadata` before it's emitted. This is deliberately
  conservative/pattern-based rather than an ML PII detector: false
  positives are cheap here (it only touches analytics metadata, not the
  live conversation), false negatives are the expensive failure mode, so
  the patterns lean toward over-matching plausible digit runs.
- `PaymentCaptureTool.invoke` generates one idempotency key per logical
  call and reuses it across its own internal retry attempts
  (`max_attempts`, with backoff) against the PCI-scoped service, so a
  retried request can be recognized server-side as "the one already
  processed" rather than charged again. A run of consecutive transient
  failures returns a failed `PaymentCaptureResult` rather than raising —
  dialogue_manager should never see an unhandled exception from a payment
  attempt.

## Consequences
- `shared/schemas/call_event.schema.json` and `shared/types-ts/index.ts`
  both gained `disclosure_acknowledged` and `degraded` as valid
  `eventType` values — any consumer of the event stream (the admin
  dashboard, analytics) needs to handle them, not just the five original
  types.
- The idempotency protection covers "agent-core retries its own call to
  the PCI service" (a network blip). It explicitly does not cover a
  process crash between charging and recording the result — that would
  need the idempotency key persisted alongside call state (the same
  Redis-backed `ConversationState` from the memory-persistence work) so a
  resumed call on a different pod can detect an in-flight payment rather
  than re-invoking it. That's flagged here as follow-up work, not
  silently out of scope.
- The redaction patterns are English/digit-format agnostic (they match
  digit runs, not language), but the disclosure text is not — see
  docs/adr/0005's consequences section for the same caveat applied to
  endpointing.
