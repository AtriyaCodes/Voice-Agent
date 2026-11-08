"""Turn taking policy.

Decides, given the current VAD state and partial transcript stream,
whether the system should keep listening, interrupt itself (barge-in),
or hand the utterance to agent-core. Kept separate from VAD itself
because turn-taking policy is where product behavior differences
between tenants tend to live (for example, how aggressively a banking
IVR replacement should allow barge-in versus a more conversational
tenant).

Two things beyond simple state tracking live here, both because a real
voice agent that skips them interrupts callers constantly or leaves dead
air on the line:

1. **Endpointing**, not just VAD silence (see endpointing.py) — a VAD
   silence hangover is a *tentative* end of turn, extended once if the
   caller's partial transcript looks mid-thought.
2. **Cancellation propagation on barge-in.** Detecting that the caller
   started talking over the agent is useless if nothing downstream
   actually stops generating — `cancellation_token` is what
   dialogue_manager and the TTS stream check to abort in-flight work the
   moment barge-in happens, and `resolve_false_interruption` is what lets
   the agent resume its own sentence if the "interruption" turns out to
   have been noise (a cough, a door, a VAD false positive) rather than
   real speech.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum, auto

from voice_pipeline.endpointing import EndpointingPolicy


class TurnState(Enum):
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    AWAITING_BARGE_IN_CONFIRMATION = auto()


@dataclass
class TurnManagerConfig:
    allow_barge_in: bool = True


class TurnManager:
    def __init__(
        self,
        config: TurnManagerConfig | None = None,
        endpointing: EndpointingPolicy | None = None,
    ):
        self._config = config or TurnManagerConfig()
        self._endpointing = endpointing or EndpointingPolicy()
        self.state = TurnState.LISTENING
        self.cancellation_token = asyncio.Event()

    def on_utterance_ended(self) -> None:
        self.state = TurnState.PROCESSING
        self._endpointing.reset()

    def on_agent_started_speaking(self) -> None:
        self.state = TurnState.SPEAKING
        self.cancellation_token = asyncio.Event()

    def on_utterance_tentatively_ended(self, partial_text: str) -> bool:
        """Called when VAD reports silence long enough to be a candidate
        end-of-turn. Returns True if the turn should actually finalize
        now, False if the caller should be given more time (see
        endpointing.py)."""
        return self._endpointing.on_utterance_tentatively_ended(partial_text)

    def on_caller_started_speaking_while_agent_speaking(self) -> bool:
        """Returns True if this should interrupt the agent's current speech."""
        if self._config.allow_barge_in and self.state == TurnState.SPEAKING:
            self.state = TurnState.AWAITING_BARGE_IN_CONFIRMATION
            self.cancellation_token.set()
            return True
        return False

    def confirm_real_interruption(self) -> None:
        """A real transcript followed the barge-in — the caller meant it.
        Moves on to processing that utterance normally."""
        if self.state == TurnState.AWAITING_BARGE_IN_CONFIRMATION:
            self.on_utterance_ended()

    def resolve_false_interruption(self) -> bool:
        """No real transcript followed the barge-in within the timeout —
        it was noise, not speech. Returns True if the agent should resume
        speaking (and the caller should clear the cancellation it set)."""
        if self.state != TurnState.AWAITING_BARGE_IN_CONFIRMATION:
            return False
        self.state = TurnState.SPEAKING
        self.cancellation_token = asyncio.Event()
        return True
