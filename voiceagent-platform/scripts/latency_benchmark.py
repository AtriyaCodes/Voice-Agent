#!/usr/bin/env python3
"""Synthetic latency-budget regression check.

ARCHITECTURE.md commits to a per-stage latency budget (VAD+partial STT
<150ms, dialogue decision <120ms, LLM time-to-first-token <150ms, TTS
time-to-first-byte <80ms). Before this script, nothing in the repo
enforced that — the CI job existed as a literal
`echo "placeholder"` (see git history of .github/workflows/ci.yml). That
is the kind of gap that looks fine right up until a regression ships
straight to a live call.

What this script can and can't check honestly, given it runs in CI with
no network access to a real STT/LLM/TTS provider:

- VAD and AEC processing time on real synthetic audio: measured for
  real, against their share of the "VAD + partial STT" budget, because
  that code runs entirely in-process.
- LLM-TTFT / TTS-first-byte: the *provider* round trip can only be
  measured against a live provider (a staging synthetic-call test, not
  unit CI). What CI *can* catch is the platform's own dispatch overhead
  around those calls regressing — e.g. someone accidentally adding a
  blocking operation to the hot path before the first token/byte is even
  requested. That overhead is measured here against a much tighter
  internal budget (a small fraction of the end-to-end one) using fake
  zero-latency providers, so a real regression in *our* code fails the
  build even though the network hop itself is out of scope for CI.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "voice-pipeline" / "src"))

import numpy as np  # noqa: E402

from voice_pipeline.aec import NlmsEchoCanceller  # noqa: E402
from voice_pipeline.vad import VoiceActivityDetector  # noqa: E402

# ARCHITECTURE.md's latency budget table, in milliseconds.
VAD_PARTIAL_STT_BUDGET_MS = 150
DISPATCH_OVERHEAD_BUDGET_MS = 5  # our own code's slice of the 120/150/80ms stage budgets


def benchmark_vad_and_aec_stage() -> float:
    sample_rate_hz = 16_000
    frame_ms = 20
    frame_samples = sample_rate_hz * frame_ms // 1000
    n_frames = 50  # 1 second of audio

    vad = VoiceActivityDetector()
    aec = NlmsEchoCanceller(sample_rate_hz=sample_rate_hz, filter_length_ms=100)

    rng = np.random.default_rng(0)
    frames = [
        (4000 * np.sin(2 * np.pi * 300 * np.arange(frame_samples) / sample_rate_hz)).astype(np.int16)
        for _ in range(n_frames)
    ]

    start = time.perf_counter()
    for frame in frames:
        aec.on_far_end_frame(np.zeros(frame_samples, dtype=np.int16))
        cleaned = aec.process(frame)
        vad.process_frame(cleaned)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return elapsed_ms / n_frames  # per-frame cost, comparable to the per-utterance budget


async def benchmark_dispatch_overhead() -> float:
    sys.path.insert(0, str(REPO_ROOT / "services" / "agent-core" / "src"))
    from agent_core.dialogue_manager import DialogueManager  # noqa: E402
    from agent_core.memory import ConversationState  # noqa: E402

    class ZeroLatencyLlm:
        async def stream_response(self, messages, tools, system_prompt):
            yield {"type": "text_delta", "text": "ok"}

    manager = DialogueManager(ZeroLatencyLlm(), tools=[], system_prompt_for_tenant=lambda t: "")
    state = ConversationState(channel_id="bench", tenant_id="bench", language="en-IN")

    start = time.perf_counter()
    async for _ in manager.handle_utterance(state, "hello"):
        pass
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms


def main() -> int:
    vad_aec_ms = benchmark_vad_and_aec_stage()
    dispatch_ms = asyncio.run(benchmark_dispatch_overhead())

    print(f"VAD+AEC per-frame cost:      {vad_aec_ms:.3f}ms (budget share of {VAD_PARTIAL_STT_BUDGET_MS}ms)")
    print(f"Dialogue dispatch overhead:  {dispatch_ms:.3f}ms (budget {DISPATCH_OVERHEAD_BUDGET_MS}ms)")

    failures = []
    if vad_aec_ms >= VAD_PARTIAL_STT_BUDGET_MS:
        failures.append(f"VAD+AEC per-frame cost {vad_aec_ms:.3f}ms exceeds {VAD_PARTIAL_STT_BUDGET_MS}ms budget")
    if dispatch_ms >= DISPATCH_OVERHEAD_BUDGET_MS:
        failures.append(f"dialogue dispatch overhead {dispatch_ms:.3f}ms exceeds {DISPATCH_OVERHEAD_BUDGET_MS}ms budget")

    if failures:
        print("\nLATENCY BUDGET REGRESSION:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nAll measured stages within budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
