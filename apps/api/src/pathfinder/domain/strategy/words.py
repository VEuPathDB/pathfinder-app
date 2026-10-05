"""The words of a phrase: its runs of letters and digits."""

from __future__ import annotations

import itertools
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


def _names_evidence(words: list[str], size: int) -> bool:
    """Whether a run is short enough to be the whole phrase, or holds three
    consecutive words of which two are not filler."""
    return size < _RUN or any(
        sum(w not in FILLER_WORDS for w in words[k : k + size]) >= _CONTENT_IN_A_RUN
        for k in range(len(words) - size + 1)
    )


def stated_run_of(prose: str, phrase: str) -> str:
    """The longest run of the prose that goes word for word with the phrase, in
    the prose's own spelling. A run holds the whole phrase, or three consecutive
    words of it of which two are not filler. Empty when the prose holds none."""
    wanted = words_of(phrase)
    if not wanted:
        return ""
    tokens = list(WORD.finditer(prose))
    held = [token.group().casefold() for token in tokens]
    size = min(_RUN, len(wanted))
    best_start, best_length = 0, 0
    for start, offset in itertools.product(range(len(held)), range(len(wanted))):
        length = 0
        while (
            start + length < len(held)
            and offset + length < len(wanted)
            and held[start + length] == wanted[offset + length]
        ):
            length += 1
        run = held[start : start + length]
        if length > max(best_length, size - 1) and _names_evidence(run, size):
            best_start, best_length = start, length
    if not best_length:
        return ""
    last = best_start + best_length - 1
    return prose[tokens[best_start].start() : tokens[last].end()]


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


def names_a_run_of(prose: str, phrase: str) -> bool:
    """Whether the prose holds the phrase whole, or three consecutive words of it
    of which two are not filler. A phrase with no words is held by any prose."""
    return not words_of(phrase) or bool(stated_run_of(prose, phrase))


__all__ = [
    "FILLER_WORDS",
    "WORD",
    "names_a_run_of",
    "numeral",
    "spelled_words",
    "stated_run_of",
    "whole_run_of",
    "words_of",
]
