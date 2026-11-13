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
_QUOTED = re.compile(r'"([^"]*)"')
# The words a researcher uses to ask that a term match as one phrase.
_ASKS_FOR_THE_PHRASE = re.compile(
    r"\b(?:exact\s+phrase|the\s+phrase|as\s+a\s+phrase|in\s+quotes)\b",
    re.IGNORECASE,
)


def _unquoted(quoted: re.Match[str]) -> str:
    """The quoted run without its quotes when it is several words."""
    inner = quoted.group(1)
    return inner if len(inner.split()) > 1 else quoted.group(0)


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

    def words_reading(self) -> str | None:
        """The text with the quotes around each phrase of several words removed,
        else None when the text quotes no such phrase."""
        read = _QUOTED.sub(_unquoted, self.text)
        return None if read == self.text else read


def asks_for_the_phrase(messages: Sequence[str]) -> bool:
    """Whether a message asks that the text term match as one phrase."""
    return any(_ASKS_FOR_THE_PHRASE.search(message) for message in messages)


def unquoted_phrase_refusal(
    name: str, search_name: str, text: str, messages: Sequence[str]
) -> str | None:
    """Why a text term of several words sent unquoted is refused when a message
    asks for the phrase, else None."""
    quoted = TextExpression(text=text).phrase_reading()
    if quoted is None or not asks_for_the_phrase(messages):
        return None
    return (
        f"{name} on {search_name}: the request asks for the phrase, so the term "
        f"is quoted: {quoted}; an unquoted term matches any of its words."
    )


__all__ = ["TextExpression", "asks_for_the_phrase", "unquoted_phrase_refusal"]
