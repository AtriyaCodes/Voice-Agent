"""Turn-completion policy layered on top of raw VAD silence detection.

VAD silence alone is a poor end-of-turn signal: a caller who pauses
mid-thought ("I need to... [pause] ...check my balance") produces the
exact same silence-frame signature as a caller who is actually done
talking. Treating every VAD silence hangover as a hard end-of-turn is
what makes voice agents interrupt people constantly in production — this
is one of the most commonly reported production complaints about
naively-built voice agents.

`EndpointingPolicy` treats VAD's silence detection as a *tentative*
end-of-turn and layers a lightweight completeness heuristic over the
caller's partial transcript on top of it: if the utterance so far reads
as obviously unfinished (trailing conjunction, trailing filler word,
trailing comma), the hangover window is extended once rather than
finalizing immediately. This is intentionally a heuristic, not a trained
classifier — see the module's ADR (docs/adr/0005) for why that's an
acceptable v1 and what the upgrade path (a small semantic
completeness/turn-detection model) looks like.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TRAILING_INCOMPLETE_WORDS = frozenset(
    {
        "and", "but", "or", "so", "because", "if", "when", "while", "that",
        "which", "who", "to", "for", "with", "of", "in", "on", "at", "as",
        "the", "a", "an", "is", "was", "my", "i", "um", "uh", "like",
        "can", "could", "would", "should", "let", "need",
    }
)


@dataclass
class EndpointingConfig:
    max_extensions: int = 1
    """How many times the hangover window can be extended for one
    utterance before finalizing regardless of apparent completeness —
    caps worst-case added latency from the heuristic being wrong."""


def looks_incomplete(partial_text: str) -> bool:
    """Cheap heuristic: does this text read like the speaker was cut off?"""
    stripped = partial_text.strip()
    if not stripped:
        return True
    if stripped.endswith((",", "-", "and", "...")):
        return True
    last_word = re.split(r"\s+", stripped.lower())[-1].strip(".,!?")
    return last_word in _TRAILING_INCOMPLETE_WORDS


class EndpointingPolicy:
    """Decides, given a VAD-tentative end-of-turn, whether to actually
    finalize the turn or extend listening a bit longer."""

    def __init__(self, config: EndpointingConfig | None = None):
        self._config = config or EndpointingConfig()
        self._extensions_used = 0

    def on_utterance_tentatively_ended(self, partial_text: str) -> bool:
        """Returns True if the turn should finalize now, False if the
        caller should be given more time to keep talking."""
        if self._extensions_used >= self._config.max_extensions:
            self._extensions_used = 0
            return True
        if looks_incomplete(partial_text):
            self._extensions_used += 1
            return False
        self._extensions_used = 0
        return True

    def reset(self) -> None:
        self._extensions_used = 0
