"""A question the researcher asks, or a comparison they ask for, is answered in
the reply; it is never a requirement of the strategy, so a check files no row
that restates one."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.strategy.words import words_of

_SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


class ResearcherAsk(CamelModel):
    """A part of a researcher's message the intent gate read as asking for an
    answer and not for records; the whole message when it read a question."""

    model_config = ConfigDict(frozen=True)

    message: str
    text: str


def _sentences(text: str) -> list[str]:
    return _SENTENCE_END.split(text.strip())


def _asked_words(
    messages: Sequence[str], asks: Sequence[ResearcherAsk]
) -> set[tuple[str, ...]]:
    """The words of each ask, of each sentence of an ask, and of each sentence
    a message ends with a question mark."""
    return {
        tuple(words_of(text))
        for text in [
            *(ask.text for ask in asks),
            *(sentence for ask in asks for sentence in _sentences(ask.text)),
            *(
                sentence
                for message in messages
                for sentence in _sentences(message)
                if sentence.endswith("?")
            ),
        ]
    }


def without_questions(
    review: VerificationReview,
    messages: Sequence[str],
    asks: Sequence[ResearcherAsk] = (),
) -> VerificationReview:
    """The review with no row that restates an ask word for word.

    A row whose words an ask only holds among others is a requirement the
    message also states, so an ask erases no row but its own restatement.
    """
    asked = _asked_words(messages, asks)
    rows = [
        row for row in review.requirements if tuple(words_of(row.text)) not in asked
    ]
    if len(rows) == len(review.requirements):
        return review
    return review.model_copy(update={"requirements": rows})


__all__ = ["ResearcherAsk", "without_questions"]
