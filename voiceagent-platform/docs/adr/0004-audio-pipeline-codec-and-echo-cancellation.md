# 4. Audio pipeline codec, resampling, jitter buffer, and echo cancellation

## Status
Accepted

## Context
Several parts of the original scaffold assumed telephony audio behaved
like a clean, in-order, 16kHz PCM stream. In practice:

- SIP/RTP telephony audio is G.711 (mu-law or A-law) at **8kHz**, not
  16kHz — voice-pipeline (STT/TTS/VAD) is written against 16kHz PCM
  because that's what the ML ecosystem around it expects.
- Carrier and PBX networks reorder and drop UDP packets. Feeding STT a
  raw, gap-having frame stream measurably hurts transcription accuracy
  and desyncs turn-taking timing.
- The agent's own synthesized speech leaks back into the inbound signal
  (through the telephony hybrid, or a caller on speakerphone). Without
  removing it, VAD cannot tell "the caller interrupted" from "the agent
  is hearing itself," and either false-triggers barge-in constantly or
  lets STT transcribe the agent's own words back at it.

## Decision
telephony-gateway owns the wire-format boundary; voice-pipeline stays
16kHz PCM internally and never has to know about telephony specifics:

- `telephony_gateway/codec.py`: G.711 mu-law/A-law <-> 16-bit PCM, plus
  8kHz<->16kHz linear-interpolation resampling. Implemented directly
  (not via the standard library's `audioop`, which was removed in Python
  3.13 — see the module docstring) and validated by round-trip/
  correlation tests against CPython's `audioop` reference behavior during
  development.
- `telephony_gateway/jitter_buffer.py`: a sequence/timestamp-aware buffer
  with a bounded reordering window and last-good-frame packet-loss
  concealment (decayed repeat, not a generative PLC model — G.711 has no
  built-in PLC the way Opus does; this is the standard "cheap" fallback
  most SIP media stacks use for this codec).
- `telephony_gateway/rtp_stream.py`: real RTP packetization (sequence
  number, timestamp, SSRC per RFC 3550) in both directions, replacing
  what was previously an unimplemented stub.
- `voice_pipeline/aec.py`: an `EchoCanceller` protocol with a real NLMS
  adaptive-filter implementation, applied to every inbound frame *before*
  VAD ever sees it (see `pipeline.py`'s `handle_inbound_audio`). The
  agent's own outbound TTS audio is fed back in as the echo reference via
  `on_far_end_frame`.

## Consequences
- The NLMS AEC here is a working reference implementation, not a
  production WebRTC-grade one (no double-talk detection, no nonlinear
  residual echo suppression). A production deployment should evaluate
  swapping in `webrtc-audio-processing` bindings behind the same
  `EchoCanceller` protocol — the pipeline's ordering (AEC before VAD)
  does not need to change to make that swap.
- The jitter buffer trades a small amount of added latency (its
  `target_depth`, in 20ms frames) for reordering tolerance. That knob sits
  inside the platform's overall VAD+STT latency budget
  (ARCHITECTURE.md) and should be tuned per deployment's actual network
  conditions, not left at the default forever.
- Linear-interpolation resampling is acceptable specifically because
  G.711 is already band-limited to ~3.4kHz — this reasoning would not
  hold if a wideband codec (Opus, G.722) were added later; that would
  need a real anti-aliasing resampler.
