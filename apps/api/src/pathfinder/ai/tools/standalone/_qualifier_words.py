"""The values one parameter proposal names, and the light stem a word is
compared by, so a word and its plural or its adjective read alike."""

from __future__ import annotations

# A stem shorter than this is a function word or a code.
_MIN_STEM = 4
_SUFFIXES = (
    "ically",
    "ation",
    "ness",
    "ical",
    "ing",
    "ies",
    "ied",
    "ed",
    "es",
    "ic",
    "al",
    "ly",
    "e",
    "s",
    "y",
)


def proposal_values(proposal: str | list[str] | None) -> list[str]:
    """The values one parameter proposal names: none, one, or a list."""
    match proposal:
        case None:
            return []
        case str():
            return [proposal]
        case list():
            return proposal


def stem(word: str) -> str:
    """The word without the one suffix that leaves at least ``_MIN_STEM`` letters."""
    lowered = word.casefold()
    for suffix in _SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) - len(suffix) >= _MIN_STEM:
            return lowered[: -len(suffix)]
    return lowered


__all__ = ["proposal_values", "stem"]
