"""A question the researcher asks, or a comparison they ask for, is answered in
the reply; it is never a requirement of the strategy, so a check files no row
for it."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import message_states

_SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


class ResearcherAsk(CamelModel):
    """A part of a researcher's message the intent gate read as asking for an
    answer and not for records; the whole message when it read a question."""

    model_config = ConfigDict(frozen=True)

    message: str
    text: str
    # The gate read the whole message as a question.
    question: bool = False

    def files_no_row(self, row: RequirementCheck, stated_in: str | None) -> bool:
        """Whether the row is this ask: a row of a message read as a question
        whose words the message carries, or a row that restates the ask."""
        if self.question and self.message == stated_in:
            return message_states(self.text, row.text)
        return message_states(self.text, row.text) and message_states(
            row.text, self.text
        )


def _questions(messages: Sequence[str]) -> list[str]:
    return [
        sentence
        for message in messages
        for sentence in _SENTENCE_END.split(message.strip())
        if sentence.endswith("?")
    ]


def _asks(row: RequirementCheck, questions: Sequence[str]) -> bool:
    """Whether the row is a question: it ends with one, or it and a question
    the researcher wrote carry each other's words."""
    return row.text.rstrip().endswith("?") or any(
        message_states(q, row.text) and message_states(row.text, q) for q in questions
    )


def _asked(
    row: RequirementCheck, messages: Sequence[str], asks: Sequence[ResearcherAsk]
) -> bool:
    stated_in = messages[row.turn - 1] if row.turn <= len(messages) else None
    return any(ask.files_no_row(row, stated_in) for ask in asks)


def without_questions(
    review: VerificationReview,
    messages: Sequence[str],
    asks: Sequence[ResearcherAsk] = (),
) -> VerificationReview:
    """The review with no row for a question the researcher asked or for a
    part of a message the gate read as an ask."""
    questions = _questions(messages)
    rows = [
        row
        for row in review.requirements
        if not _asks(row, questions) and not _asked(row, messages, asks)
    ]
    if len(rows) == len(review.requirements):
        return review
    return review.model_copy(update={"requirements": rows})


__all__ = ["ResearcherAsk", "without_questions"]
