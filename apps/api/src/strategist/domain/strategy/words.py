"""The words of a phrase: its runs of letters and digits, a number with the
minus sign written before it."""

from __future__ import annotations

import re

WORD = re.compile(r"(?:(?<![a-z0-9])-(?=[0-9]))?[a-z0-9]+", re.IGNORECASE)


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

# A number word up to twenty reads as its digits, since a count is written
# either way and the site takes only digits.
_NUMERALS = {
    word: str(n)
    for n, word in enumerate(
        (
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        )
    )
}


# An ordinal reads as its number, since "95th" states the value 95.
_ORDINAL = re.compile(r"(\d+)(?:st|nd|rd|th)")


def numeral(word: str) -> str:
    """The digits a number word or an ordinal reads as, else the word itself."""
    ordinal = _ORDINAL.fullmatch(word)
    return ordinal.group(1) if ordinal else _NUMERALS.get(word, word)


def whole_run_of(prose: str, phrase: str) -> str:
    """The run of the prose that holds every word of the phrase in order, in the
    prose's own spelling. A number word or an ordinal reads as its digits. Empty
    when no run holds the whole phrase."""
    wanted = [numeral(word) for word in words_of(phrase)]
    tokens = list(WORD.finditer(prose))
    held = [numeral(token.group().casefold()) for token in tokens]
    size = len(wanted)
    start = next(
        (
            k
            for k in range(len(held) - size + 1)
            if size and held[k : k + size] == wanted
        ),
        None,
    )
    if start is None:
        return ""
    return prose[tokens[start].start() : tokens[start + size - 1].end()]


__all__ = [
    "FILLER_WORDS",
    "WORD",
    "numeral",
    "spelled_words",
    "whole_run_of",
    "words_of",
]
