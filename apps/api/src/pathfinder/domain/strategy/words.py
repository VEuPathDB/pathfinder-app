"""The words of a phrase: its runs of letters and digits."""

from __future__ import annotations

import re

WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def spelled_words(text: str) -> list[str]:
    """The words of the phrase, in its own spelling."""
    return WORD.findall(text)


def words_of(text: str) -> list[str]:
    """The words of the phrase, case-folded."""
    return [word.casefold() for word in spelled_words(text)]


# Words that name no evidence. Every WDK gene search carries "genes", so a phrase
# that overlaps another only there names nothing.
FILLER_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "by",
        "for",
        "from",
        "gene",
        "genes",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

_RUN = 3
_CONTENT_IN_A_RUN = 2


def names_a_run_of(prose: str, phrase: str) -> bool:
    """Whether the prose holds the phrase whole, or three consecutive words of it
    of which two are not filler."""
    wanted = words_of(phrase)
    held = words_of(prose)
    size = min(_RUN, len(wanted))
    runs = {tuple(held[k : k + size]) for k in range(len(held) - size + 1)}
    return any(
        run in runs
        and (
            size < _RUN or sum(w not in FILLER_WORDS for w in run) >= _CONTENT_IN_A_RUN
        )
        for run in (tuple(wanted[k : k + size]) for k in range(len(wanted) - size + 1))
    )


__all__ = ["FILLER_WORDS", "WORD", "names_a_run_of", "spelled_words", "words_of"]
