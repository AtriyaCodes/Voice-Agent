# 3. LLM provider choice and fallback/circuit-breaker strategy

## Status
Accepted

## Context
agent-core's dialogue loop depends on one external call (the LLM) sitting
directly in the hot path of a live phone call. A stalled or erroring
provider is not an exception to log and move on from — it's dead air the
caller is sitting through — and an agent that blindly retries a failing
provider on every turn turns a provider outage into a retry storm on top
of it (each retry adds latency and burns quota while the provider is
already down).

## Decision
- Default provider is Anthropic (`services/agent-core/src/agent_core/llm_client.py`'s
  `LlmClient`), used through the streaming Messages API so text and tool-use
  events reach dialogue_manager incrementally rather than after a full
  response.
- `LlmClient` is never held directly by `DialogueManager`. It's wrapped in
  `ResilientLlmClient`, which holds an ordered list of `(name, provider)`
  fallbacks, each behind its own `CircuitBreaker` (consecutive-failure
  threshold, cooldown, half-open trial on recovery — standard breaker
  semantics, see the class for the exact state machine).
- A "thinking filler" callback fires if time-to-first-token exceeds a
  configurable threshold, so the call layer can play a natural filler
  phrase ("let me check on that") instead of silence while the LLM is
  still working — this is wired as a callback rather than baked into
  `ResilientLlmClient` so the actual filler-phrase audio/TTS trigger stays
  a voice-pipeline/agent-core integration concern, not an LLM-client one.
- When every provider in the chain is unavailable, `ResilientLlmClient`
  raises `LlmUnavailableError` rather than propagating the underlying
  provider exception. `DialogueManager.handle_utterance` catches
  specifically that and degrades the call (a canned "let me get you to
  someone who can help" response plus a `degraded` `CallEvent`) instead of
  letting the call hang up on an unhandled exception.

## Consequences
- Adding a second provider (e.g. an on-prem model for an air-gapped
  deployment) is a config change — construct another `LlmProvider` and add
  it to the fallback list — not a dialogue_manager change, since
  dialogue_manager only ever depends on the `LlmProvider` protocol.
- The circuit breaker's failure threshold and cooldown are per-deployment
  tuning knobs, not fixed constants, because how aggressively to fail over
  is itself a product decision (a banking tenant may want to fail over
  faster and accept a lower-quality on-prem fallback rather than risk dead
  air; a best-effort tenant may prefer to wait longer for the primary).
- This does not include response caching or a fully local last-resort
  model — the documented last line of defense if *every* configured
  provider (including any on-prem fallback) is down is the degraded
  response and a warm handoff, which is a deliberate choice: for a
  banking voice agent, "hand off to a human" is a safer failure mode than
  "answer from a stale cache."
