"""A question the Lead's card asks, and the dimension its answer states."""

from __future__ import annotations

from assistant_core.graph.turn_state import ConsultQuestion
from pydantic import Field, model_validator

from pathfinder.domain.reference_grammar import A_REFERENCE
from pathfinder.domain.strategy.constraints import CONSTRAINT_KINDS, ConstraintKind


class CardQuestion(ConsultQuestion):
    """A question card, and the dimension its answer states."""

    dimension: ConstraintKind = Field(
        default=ConstraintKind.OTHER,
        description=(
            f"The dimension the answer states, one of {CONSTRAINT_KINDS}. A "
            "recorded question keeps the dimension its `cardQuestions` entry names."
        ),
    )

    @model_validator(mode="after")
    def _is_written_for_the_researcher(self) -> CardQuestion:
        """A question is read by the researcher, so it carries no reference.

        A reference renders in the reply from the turn's facts; a card arrives
        before the facts exist, so a value a question states is written in
        words from the sheet the pass read.
        """
        texts = [self.prompt, self.context, *(o.label for o in self.options)]
        found = [m.group() for text in texts for m in A_REFERENCE.finditer(text or "")]
        if found:
            msg = (
                f"the question {self.prompt!r} carries the reference(s) {found}; a "
                "card is read by the researcher before the facts exist, so write the "
                "value in words from the sheet you read"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _offers_a_choice(self) -> CardQuestion:
        """A question that offers options offers two at least, each its own label.

        One with none is answered in the researcher's words.
        """
        labels = [option.label for option in self.options]
        if len(set(labels)) < len(labels):
            msg = f"the question {self.prompt!r} offers the labels {labels} more than once"
            raise ValueError(msg)
        if len(labels) == 1:
            msg = (
                f"the question {self.prompt!r} offers 1 option {labels}, which is no "
                f"choice: offer two options at least that each change something, or "
                f"none for an answer in the researcher's words"
            )
            raise ValueError(msg)
        return self
