"""A question the Lead's card asks, and the dimension its answer states."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.graph.turn_state import ConsultQuestion
from pydantic import Field, model_validator

from strategist.domain.reply_note import A_RECORD
from strategist.domain.strategy.constraints import (
    CONSTRAINT_KINDS,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.question_options import Keep, TypedOption, Withdraw
from strategist.domain.strategy.questions import requirement_choices
from strategist.domain.strategy.requirement_reports import numbered_requirements


class CardQuestion(ConsultQuestion):
    """A question card, and the dimension its answer states."""

    dimension: ConstraintKind = Field(
        default=ConstraintKind.UNTYPED,
        description=(
            f"The dimension the answer states, one of {CONSTRAINT_KINDS}. A "
            "recorded question keeps the dimension its `cardQuestions` entry names."
        ),
    )
    requirement: str = Field(
        default="",
        description=(
            "The id of the requirement the question asks about, as the ledger "
            "names it, or the id of the criterion whose value it asks for, or "
            "empty. A recorded question on the same requirement or criterion is "
            "asked in its place."
        ),
    )

    replaces: list[str] = Field(
        default_factory=list,
        description=(
            "The numbers, such as R2, of the requirements in the ledger's list "
            "that a stand-in the answer names takes the place of. Empty unless "
            "the question asks for a stand-in."
        ),
    )

    def recommended_drops(
        self,
        requirements: Sequence[Constraint],
        links: Mapping[str, Sequence[str]],
    ) -> list[str]:
        """Why a recommended pick would retire or replace a hard stated requirement:
        its drop option, or any option but its keep on a question that replaces it,
        names it, or names a criterion ``links`` ties to it on the question's dimension."""
        recommended = [o.label for o in self.options if o.recommended]
        if not recommended:
            return []
        choices = requirement_choices(requirements)
        kinds = {c.id: c.kind for c in requirements}
        answered_here = [
            rid
            for rid in links.get(self.requirement, ())
            if kinds.get(rid) is self.dimension
        ]
        tagged = {*self.replaces, self.requirement, *answered_here}
        found: list[str] = []
        for number, held in numbered_requirements(requirements).items():
            if held.source is not ConstraintSource.USER_EXPLICIT or not held.hard:
                continue
            drop = _label_of(choices, Withdraw(constraint_id=held.id))
            keep = _label_of(choices, Keep(constraint_id=held.id))
            answered = bool(tagged & {number, held.id})
            changing = [
                label
                for label in recommended
                if label == drop or (answered and label != keep)
            ]
            if changing:
                found.append(
                    f"{number} is the researcher's requirement "
                    f"'{held.requested_value}'. A card offers dropping it as "
                    f"'{drop}' and recommends no option that drops or replaces it: "
                    f"the question recommends {', '.join(repr(x) for x in changing)}. "
                    f"Recommend '{keep}' or no option."
                )
        return found

    @model_validator(mode="after")
    def _is_written_for_the_researcher(self) -> CardQuestion:
        """A card arrives before the facts that link a record, so a question
        names a record in words."""
        texts = [self.prompt, self.context, *(o.label for o in self.options)]
        found = [
            m.group().strip() for text in texts for m in A_RECORD.finditer(text or "")
        ]
        if found:
            msg = (
                f"the question {self.prompt!r} carries the reference(s) {found}; a "
                "card is read before the facts that link it exist, so name the "
                "record in words"
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


def _label_of(choices: Mapping[str, TypedOption], binding: Withdraw | Keep) -> str:
    return next(label for label, option in choices.items() if option.binding == binding)
