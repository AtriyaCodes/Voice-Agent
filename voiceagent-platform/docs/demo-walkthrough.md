# Call walkthrough: what actually runs, end to end

A step-by-step trace of one inbound banking call, naming the real code
path each step now hits. Useful for a live walkthrough without a SIP
trunk in front of you — every stage below is backed by a passing test in
that module's `tests/` directory.

## 1. Call arrives, tenant resolved, disclosure spoken

- `SipHandler.handle_stasis_start` (`telephony_gateway/sip_handler.py`)
  answers the channel and resolves a tenant id from the SIP dialplan
  channel variable.
- Before trusting that, `SessionOrchestrator.startSession`
  (`orchestration-api/src/services/sessionOrchestrator.ts`) cross-checks
  the SIP trunk the call actually arrived on against that tenant's
  `allowedSipTrunks` — a dialplan misconfiguration or spoofed trunk header
  no longer silently lands a call in the wrong tenant's context
  (`docs/adr` — this is the fix for the "tenant boundary trusts the SIP
  layer" gap; test: `sessionOrchestrator.test.ts`).
- For a `banking`-mode tenant, `DialogueManager.start_call`
  (`agent_core/dialogue_manager.py`) yields the RBI/DPDP-mandated
  recording+AI disclosure as the first spoken turn and emits a
  `disclosure_acknowledged` `CallEvent` (`agent_core/compliance.py`;
  test: `test_dialogue_manager.py::test_start_call_emits_disclosure_for_banking_tenants_only`).

## 2. Caller speaks; audio is cleaned before anything decides what it means

- RTP packets arrive at `RtpStream.on_inbound_packet`
  (`telephony_gateway/rtp_stream.py`), get depacketized, buffered through
  `JitterBuffer` (reordering + loss concealment), and decoded from G.711
  8kHz to 16kHz PCM by `TelephonyCodec` — none of this was implemented
  before this pass; `test_rtp_stream.py` includes a real UDP-loopback
  round trip.
- `VoicePipeline.handle_inbound_audio` (`voice_pipeline/pipeline.py`) runs
  every frame through `NlmsEchoCanceller.process` *before* VAD ever sees
  it (`voice_pipeline/aec.py`) — this is what stops the agent's own TTS
  output from being misread as the caller barging in.

## 3. Caller pauses mid-sentence — the agent does not interrupt

- STT reports a "final" transcript on the pause. `TurnManager
.on_utterance_tentatively_ended` routes it through `EndpointingPolicy`
  (`voice_pipeline/endpointing.py`), which recognizes "I need to check
  my..." as incomplete and extends the hangover once instead of handing
  it to agent-core; test:
  `test_pipeline.py::test_endpointing_extends_past_a_mid_thought_pause`.

## 4. Caller finishes; agent-core replies, LLM is slow

- The finalized utterance reaches `DialogueManager.handle_utterance`,
  which calls `ResilientLlmClient.stream_response`
  (`agent_core/llm_client.py`). If time-to-first-token exceeds the
  configured threshold, the `on_slow_ttft` callback fires — the
  integration point for a "let me check on that" filler phrase instead of
  dead air; test:
  `test_llm_client.py::test_resilient_client_fires_filler_callback_on_slow_first_token`.

## 5. Caller barges in mid-response

- VAD detects real speech energy while `TurnManager.state == SPEAKING`,
  calling `on_caller_started_speaking_while_agent_speaking`, which sets
  `cancellation_token` and moves to `AWAITING_BARGE_IN_CONFIRMATION`.
- Both `DialogueManager.handle_utterance` and
  `VoicePipeline.synthesize_response` check that token every loop
  iteration and stop generating immediately — text and audio, not just a
  state flag; tests:
  `test_dialogue_manager.py::test_handle_utterance_stops_immediately_on_barge_in_cancellation`,
  `test_pipeline.py::test_synthesize_response_stops_yielding_once_barge_in_cancels`.
- If no real transcript follows (a cough, a VAD false positive),
  `resolve_false_interruption` resumes the agent's speech with a fresh
  token instead of leaving the call in silence; test:
  `test_turn_manager.py::test_false_interruption_resumes_speaking_with_a_fresh_cancellation_token`.

## 6. Caller asks to pay a bill

- The LLM emits a `capture_payment` tool-use block.
  `DialogueManager._invoke_tool` binds `channel_id` from call state (not
  from the model) and merges it with the model-supplied
  `amount_cents`/`currency` — fixing the original code's assumption that
  the LLM would supply `channel_id` itself, which it never could; test:
  `test_dialogue_manager.py::test_handle_utterance_binds_channel_id_and_merges_llm_tool_input`.
- `PaymentCaptureTool.invoke` (`agent_core/tools/payment_capture.py`)
  generates one idempotency key and reuses it across its own retry
  attempts against the PCI-scoped service, so a client-side timeout can't
  turn into a double charge; test: `test_payment_capture.py`.

## 7. LLM provider goes down mid-call

- `ResilientLlmClient` falls back to the next configured provider; if all
  providers are unavailable, it raises `LlmUnavailableError`, which
  `DialogueManager.handle_utterance` catches specifically — the caller
  hears a degraded response ("let me get you to someone who can help")
  and a `degraded` `CallEvent` is emitted, not a dropped call; test:
  `test_dialogue_manager.py::test_handle_utterance_degrades_gracefully_when_llm_is_unavailable`.

## 8. Call runs long

- `ConversationState.summarize_if_over_budget`
  (`agent_core/memory.py`) collapses older turns into one summary turn
  once the conversation's approximate token count passes budget, keeping
  the LLM's context (and therefore its time-to-first-token) from growing
  unbounded over a 10+ minute call; test: `test_memory.py`.
- The same `ConversationState` now actually round-trips through Redis
  (`save`/`load`), matching what its docstring already claimed but the
  original implementation didn't do.

## What to run to see all of this pass

```bash
make test   # all five services, including every test named above
python scripts/latency_benchmark.py   # the VAD+AEC and dispatch-overhead budget check that replaced the CI placeholder
```
