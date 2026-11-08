# PCI scope and payment capture isolation

## Principle

Cardholder data never enters the general conversation path, the LLM's
context, or any log/transcript store used for QA or analytics. This is
enforced as a service boundary, not as a prompt instruction to the model.

## How it works

1. agent-core detects, from the conversation, that a payment needs to be
   collected and calls the `capture_payment` tool
   (`services/agent-core/src/agent_core/tools/payment_capture.py`).
2. That tool call is a handoff, not a data exchange: agent-core passes an
   amount and currency, nothing else.
3. The isolated, PCI-scoped payment service takes over the call leg
   directly (DTMF capture or a dedicated secure audio prompt), collects
   card data itself, and never returns it to agent-core, voice-pipeline,
   or orchestration-api.
4. The payment service returns only a boolean result and a tokenized
   payment reference. That is the only payment-related data that ever
   reaches conversation state, logs, or transcripts.

## Scope boundary

Everything in `services/` other than the isolated payment service itself
is out of PCI DSS scope for cardholder data, because none of those
services ever handle, store, transmit, or process cardholder data. The
isolated payment service is intentionally not included in this
repository's service list; it is a separately scoped, separately
audited component, and its own repository and deployment pipeline
should be treated with PCI DSS controls (network segmentation, access
logging, key management) that do not apply to the rest of VoiceAgent.

## Multi-tenant note

For banking tenants, this same isolation model is what allows
full front-to-back data segregation between tenants: tenant context
never crosses into the payment service's own scope, and the payment
service has no need to know which tenant it is serving beyond routing.
