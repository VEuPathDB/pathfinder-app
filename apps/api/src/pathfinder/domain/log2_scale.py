"""The scale a parameter's value is on, log2 or fold, and the value a message
states on the other scale, read in the parameter's own."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Literal, NamedTuple

Scale = Literal["log2", "fold"]

# A display name that names the log2 scale holds a log2 value; one that names
# a fold, and no log2, holds a fold.
_LOG2 = re.compile(r"\blog\s*2(?![\d.])", re.IGNORECASE)
_FOLD = re.compile(r"\bfold\b", re.IGNORECASE)
_NUMBER = r"(\d+(?:\.\d+)?)"
# A number on the log2 scale follows the scale's name within one short clause.
_LOG2_PHRASE = re.compile(
    rf"\blog\s*2(?![\d.])[^\d.,;]{{0,30}}?{_NUMBER}", re.IGNORECASE
)
# A fold is a number joined to the word, or a number that follows "fold change".
_FOLD_PHRASES = (
    re.compile(rf"{_NUMBER}\s*-?\s*fold\b", re.IGNORECASE),
    re.compile(rf"\bfold[\s-]*change[^\d.,;]{{0,20}}?{_NUMBER}", re.IGNORECASE),
)
# A fold written with three significant digits comes back from a log2 value
# written at three decimals.
_LOG2_DECIMALS = 3
_MOST_DECIMALS = 15


class StatedNumber(NamedTuple):
    """A number a message writes on one scale, and the words that write it."""

    number: float
    scale: Scale
    words: str
    start: int
    end: int


def scale_of(display_name: str) -> Scale | None:
    """The scale a parameter's display name names, if any."""
    if _LOG2.search(display_name):
        return "log2"
    if _FOLD.search(display_name):
        return "fold"
    return None


def _overlaps(found: StatedNumber, held: Sequence[StatedNumber]) -> bool:
    return any(found.start < h.end and h.start < found.end for h in held)


def stated_numbers(text: str) -> list[StatedNumber]:
    """Each number the text writes on the log2 scale or as a fold, in order.

    A fold change named after "log2" is on the log2 scale. A fold is a
    positive ratio, so a fold of zero is no number on either scale.
    """
    found = [
        StatedNumber(float(m.group(1)), "log2", m.group(), m.start(), m.end())
        for m in _LOG2_PHRASE.finditer(text)
    ]
    for phrase in _FOLD_PHRASES:
        for m in phrase.finditer(text):
            fold = StatedNumber(
                float(m.group(1)), "fold", m.group(), m.start(), m.end()
            )
            if fold.number > 0 and not _overlaps(fold, found):
                found.append(fold)
    return sorted(found, key=lambda s: s.start)


def on_scale(number: float, stated: Scale, site: Scale) -> float:
    """A number written on one scale, written on the site's."""
    if stated == site:
        return number
    if site == "log2":
        return round(math.log2(number), _LOG2_DECIMALS)
    return 2**number


def _decimals(value: float) -> int:
    """The fewest decimals that write the value exactly."""
    return next(
        (d for d in range(_MOST_DECIMALS) if round(value, d) == value),
        _MOST_DECIMALS,
    )


def _on_the_other_scale(display_name: str, texts: Sequence[str]) -> list[StatedNumber]:
    site = scale_of(display_name)
    return [
        stated
        for text in texts
        for stated in stated_numbers(text)
        if site is not None and stated.scale != site
    ]


def in_the_sites_scale(
    number: float, display_name: str, texts: Sequence[str]
) -> StatedNumber | None:
    """The words of a message that write this number on the scale the
    parameter's display name does not name, or None."""
    return next(
        (s for s in _on_the_other_scale(display_name, texts) if s.number == number),
        None,
    )


def stated_on_the_other_scale(
    value: float, display_name: str, texts: Sequence[str]
) -> str:
    """The words of a message that state this value on the other scale: a log2
    0.585 is stated by "1.5-fold", which it gives back at the decimals the fold
    is written with. Empty when no message states it so."""
    site = scale_of(display_name)
    if site is None:
        return ""
    return next(
        (
            s.words
            for s in _on_the_other_scale(display_name, texts)
            if round(on_scale(value, site, s.scale), _decimals(s.number)) == s.number
        ),
        "",
    )


def without_the_other_scale(text: str, display_name: str) -> str:
    """The text with each number it writes on the other scale blanked, so a
    fold's number never states a log2 value, nor a log2 number a fold."""
    for stated in reversed(_on_the_other_scale(display_name, [text])):
        text = (
            text[: stated.start]
            + " " * (stated.end - stated.start)
            + text[stated.end :]
        )
    return text


def fold_label(display_name: str, value: str) -> str:
    """The fold a numeric value of a log2 parameter stands for, else nothing."""
    if scale_of(display_name) != "log2":
        return ""
    try:
        exponent = float(value)
    except ValueError:
        return ""
    return f"{2**exponent:.3g}-fold"


__all__ = [
    "Scale",
    "StatedNumber",
    "fold_label",
    "in_the_sites_scale",
    "on_scale",
    "scale_of",
    "stated_numbers",
    "stated_on_the_other_scale",
    "without_the_other_scale",
]
