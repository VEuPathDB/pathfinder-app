"""A free-text expression the site search reads: operands joined by operator
words, each operand a run of words."""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

_OPERATORS = frozenset({"AND", "OR", "NOT"})
# A text that holds one of these is grouped by its writer.
_GROUPING = frozenset('"()')
_WILDCARD = "*"
# The words a researcher uses to ask that a term match as one phrase.
_ASKS_FOR_THE_PHRASE = re.compile(
    r"\b(?:exact\s+phrase|the\s+phrase|as\s+a\s+phrase|in\s+quotes)\b",
    re.IGNORECASE,
)


def _phrased(operand: list[str]) -> str:
    """The operand quoted when it is several words and holds no wildcard."""
    text = " ".join(operand)
    if len(operand) > 1 and not any(_WILDCARD in word for word in operand):
        return f'"{text}"'
    return text


class TextExpression(BaseModel):
    """One text as written, read as operands joined by operator words."""

    model_config = ConfigDict(frozen=True)

    text: str

    def phrase_reading(self) -> str | None:
        """The text with each operand of several words quoted, else None when
        no operand is quoted or the writer grouped the text."""
        if _GROUPING & set(self.text):
            return None
        runs = [
            list(words)
            for _, words in itertools.groupby(
                self.text.split(), key=lambda word: word in _OPERATORS
            )
        ]
        read = " ".join(
            " ".join(run) if run[0] in _OPERATORS else _phrased(run) for run in runs
        )
        return None if read == " ".join(self.text.split()) else read


def asks_for_the_phrase(messages: Sequence[str]) -> bool:
    """Whether a message asks that the text term match as one phrase."""
    return any(_ASKS_FOR_THE_PHRASE.search(message) for message in messages)


__all__ = ["TextExpression", "asks_for_the_phrase"]
