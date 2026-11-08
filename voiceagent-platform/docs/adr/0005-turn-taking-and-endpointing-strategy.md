# 5. Turn-taking / endpointing strategy

## Status
Accepted

## Context
The original VAD implementation treated a silence hangover as end-of-turn
directly. That is the single most commonly reported production complaint
about naively-built voice agents: a caller who pauses mid-thought ("I
need to... check my balance") produces the same silence-frame signature
as a caller who is actually finished, and the agent barges in on its own
caller.

Barge-in itself had the mirror-image problem: `TurnManager` had a method
to *detect* the caller talking over the agent, but nothing downstream
actually stopped generating — the in-flight LLM stream and TTS synthesis
kept running regardless.

## Decision
- `voice_pipeline/endpointing.py`'s `EndpointingPolicy` treats a VAD/STT
  "final" as a *tentative* end-of-turn. A cheap heuristic
  (`looks_incomplete`: trailing conjunction, filler word, or comma) can
  extend the hangover once before finalizing, bounded by
  `EndpointingConfig.max_extensions` so a wrong heuristic call has a
  bounded worst-case latency cost rather than an unbounded one.
- This is explicitly a heuristic, not a trained model. The upgrade path
  is a small semantic completeness/turn-detection classifier behind the
  same `on_utterance_tentatively_ended(partial_text) -> bool` interface —
  nothing above `TurnManager` needs to change to swap it in.
- `TurnManager.cancellation_token` (an `asyncio.Event`) is set the moment
  barge-in is detected. `DialogueManager.handle_utterance` and
  `VoicePipeline.synthesize_response` both check it on every loop
  iteration and stop immediately rather than continuing to generate text
  or audio the caller has already talked over.
- Barge-in is not assumed to be real speech until confirmed:
  `TurnManager` has an `AWAITING_BARGE_IN_CONFIRMATION` state.
  `confirm_real_interruption()` moves it to normal processing once a real
  transcript follows; `resolve_false_interruption()` — for a cough, a
  door, a VAD false positive with no real speech behind it — resumes the
  agent's own speech with a fresh cancellation token instead of leaving
  the call in dead air because of a false trigger.

## Consequences
- The false-interruption "resume" path resumes the agent *speaking*
  (TTS/turn state), not literally the exact LLM generation from the byte
  it was cut off at — regenerating the interrupted response from where it
  left off is a larger change (would need the partial response text
  preserved and re-submitted as a continuation) and is left as a follow-up
  if false triggers turn out to be frequent enough in practice to matter.
- `EndpointingPolicy`'s word list is English-only. A deployment serving
  Hindi or other Indian-language callers needs a language-appropriate
  completeness heuristic (or the semantic-model upgrade path above) before
  this endpointing behavior can be trusted cross-lingually — shipping the
  English heuristic as a global default for a multilingual platform would
  be worse than no heuristic in those languages.
