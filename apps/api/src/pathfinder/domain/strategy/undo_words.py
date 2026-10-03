"""Whether a message asks to take back the last change to the strategy."""

from __future__ import annotations

from pathfinder.domain.strategy.words import words_of

__all__ = ["asks_to_undo"]

_UNDO_PHRASES: tuple[tuple[str, ...], ...] = (
    ("undo",),
    ("revert",),
    ("put", "it", "back"),
    ("go", "back", "to"),
    ("roll", "back"),
)


def asks_to_undo(message: str) -> bool:
    """Whether the message holds an undo phrase as consecutive whole words."""
    held = words_of(message)
    return any(
        held[k : k + len(phrase)] == list(phrase)
        for phrase in _UNDO_PHRASES
        for k in range(len(held) - len(phrase) + 1)
    )
