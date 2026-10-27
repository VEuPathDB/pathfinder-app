"""What the assistant asks the researcher: a question, the value it
recommends, and the options it offers, each typed by what answering it binds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Annotated

from pydantic import Field, ValidationError, model_validator
from veupathdb.model import CamelModel

from pathfinder.domain.clipped import list_clipped_to, text_clipped_to
from pathfinder.domain.omitted_from_input import OmittedFromInput
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.option_labels import (
    count_at,
    option_label,
    term_of,
    value_readings,
    with_count,
)
from pathfinder.domain.strategy.question_options import (
    Keep,
    SetValues,
    TypedOption,
    Withdraw,
    binding_key,
    option_id,
    options_by_id,
    refuse_a_single_option,
)
from pathfinder.domain.strategy.readings import (
    KeysOnTheReadings,
    Reading,
    ReadValues,
)
from pathfinder.domain.strategy.words import words_of

_QUESTION_LIMIT = 300
_LABEL_LIMIT = 120
_OPTIONS_LIMIT = 8
_A_CHOICE = 2


_NO_READINGS: Mapping[str, str] = MappingProxyType({})


class _Question(CamelModel):
    """What a question asks, the dimension it decides and the value it recommends."""

    question: Annotated[str, Field(min_length=1), text_clipped_to(_QUESTION_LIMIT)]
    dimension: ConstraintKind = ConstraintKind.OTHER
    recommended_value: str = ""

    @property
    def decides_a_dimension(self) -> bool:
        """Whether the question names the dimension its answer states.

        A question recorded as bare text carries the default dimension, which
        names nothing.
        """
        return (
            bool(self.recommended_value) or self.dimension is not ConstraintKind.OTHER
        )

    def recommendation(self) -> Constraint | None:
        """The recommended value as a constraint, or None when none was offered."""
        if not self.recommended_value:
            return None
        return Constraint(
            kind=self.dimension,
            requested_value=self.recommended_value,
            label=self.question[:_LABEL_LIMIT],
            source=ConstraintSource.ASSUMED,
            hard=False,
        )


class OpenQuestion(_Question):
    """A question the assistant asked the user, and the value it recommended.

    The recommendation is typed here so the next turn reads it instead of the
    reply text that offered it. Each option carries what answering it binds.
    """

    options: list[TypedOption] = Field(default_factory=list, max_length=_OPTIONS_LIMIT)

    @model_validator(mode="after")
    def _offers_a_choice(self) -> OpenQuestion:
        """No option, or at least two, each with its own id and binding."""
        refuse_a_single_option(self.question, [o.label for o in self.options])
        ids = [option.id for option in self.options]
        if len(ids) != len(set(ids)):
            msg = f"the question offers the option ids {ids} more than once"
            raise ValueError(msg)
        bound = [binding_key(option) for option in self.options]
        if len(bound) != len(set(bound)):
            labels = [option.label for option in self.options]
            msg = (
                f"the options {labels} of {self.question!r} bind the same values, "
                f"so they are one option and the question offers no choice"
            )
            raise ValueError(msg)
        return self


class AskedQuestion(_Question):
    """A question as a model writes it: the labels of the options it offers.

    A label binds no value and is never a requirement, so the typed question
    offers none and is answered in the researcher's words.
    """

    options: Annotated[list[str], list_clipped_to(_OPTIONS_LIMIT)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def _one_option_is_a_free_text_question(self) -> AskedQuestion:
        if len(options_by_id(self.options)) == 1:
            self.options = []
        return self

    def typed(self) -> OpenQuestion:
        return OpenQuestion(
            question=self.question,
            dimension=self.dimension,
            recommended_value=self.recommended_value,
        )


class SlotQuestion(AskedQuestion):
    """A question about one parameter of one criterion, as FRAME writes it.

    Each offered value becomes an option that sets that parameter to it; a
    parameter the site offers a vocabulary for offers the vocabulary's values.
    A question that names no parameter offers no option.
    """

    criterion_id: str = ""
    param_name: str = ""
    readings: list[Reading] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    labels: Annotated[dict[str, str], OmittedFromInput] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _keys_on_the_readings_are_the_question_s(cls, data: object) -> object:
        try:
            keyed = KeysOnTheReadings.model_validate(data)
        except ValidationError:
            return data
        return keyed.on_the_question()

    @property
    def names_a_slot(self) -> bool:
        """Whether the question names the parameter and the criterion it sets."""
        return bool(self.criterion_id and self.param_name)

    def _offered(self, criterion: Criterion | None) -> list[str]:
        """The values the card offers: the vocabulary of the open slot, whole
        while it fits a card and else the offered values it holds."""
        vocabulary = next(
            (
                slot.options
                for slot in ([] if criterion is None else criterion.open_params)
                if slot.param_name == self.param_name and slot.options
            ),
            [],
        )
        if not vocabulary:
            return self.options
        if len(vocabulary) <= _OPTIONS_LIMIT:
            return vocabulary
        return [value for value in self.options if value in vocabulary]

    def _by_wire(self, criterion: Criterion | None) -> dict[str, str]:
        """Each wire value an offered value binds, under the first option naming it."""
        by_wire: dict[str, str] = {}
        for key, value in options_by_id(self._offered(criterion)).items():
            for reading in value_readings(criterion, self.param_name, value):
                by_wire.setdefault(
                    term_of(criterion, self.param_name, reading),
                    key if reading == value else option_id(reading),
                )
        return by_wire

    def offers_a_choice(self, criterion: Criterion | None) -> bool:
        """Whether the offered values bind two values at least, or none.

        A value and the site's label of it bind one term, so two such
        options are one.
        """
        return (
            bool(self.readings)
            or not self.names_a_slot
            or len(self._by_wire(criterion)) != 1
        )

    def asks_a_value_in_words(self, criterion: Criterion | None) -> bool:
        if not self.names_a_slot:
            return len(self.options) > _A_CHOICE
        if criterion is None or self.readings:
            return False
        return not criterion.why_no_readings(self.param_name)

    def typed(
        self,
        criterion: Criterion | None = None,
        *,
        noun: str = "record",
        replaces: Sequence[str] = (),
        stated: bool = False,
        readings: Mapping[str, str] = _NO_READINGS,
    ) -> OpenQuestion:
        """The question with one option per value an offered value binds.

        ``criterion`` is the one the question sets, which names the parameter
        and holds the counts measured at the offered values; ``noun`` is what
        the site counts the record type in.
        """
        if not self.names_a_slot:
            return super().typed()
        if self.readings:
            return OpenQuestion(
                question=self.question,
                dimension=self.dimension,
                recommended_value=self.recommended_value,
                options=[
                    self._read(criterion, r, noun, replaces, stated=stated)
                    for r in self.readings
                ],
            )
        by_wire = self._by_wire(criterion)
        return OpenQuestion(
            question=self.question,
            dimension=self.dimension,
            recommended_value=self.recommended_value,
            options=[
                TypedOption(
                    id=key,
                    label=option_label(
                        criterion,
                        self.param_name,
                        wire,
                        noun=noun,
                        readings={**readings, **self.labels},
                    ),
                    binding=SetValues(
                        criterion_id=self.criterion_id,
                        params={self.param_name: wire},
                    ),
                )
                for wire, key in by_wire.items()
            ],
        )

    def _read(
        self,
        criterion: Criterion | None,
        reading: Reading,
        noun: str,
        replaces: Sequence[str],
        *,
        stated: bool,
    ) -> TypedOption:
        count = count_at(criterion, self.param_name, reading.value)
        return TypedOption(
            id=option_id(reading.label),
            label=with_count(reading.label, count, noun),
            binding=ReadValues(
                criterion_id=self.criterion_id,
                params={self.param_name: reading.value},
                reading=reading.label,
                caveat=reading.caveat,
                replaces=list(replaces),
                names_no_requirement=stated and not replaces,
            ),
        )


def _withdrawal(requirement: Constraint) -> TypedOption:
    label = f"Drop {requirement.requested_value}"[:_LABEL_LIMIT]
    return TypedOption(
        id=option_id(label),
        label=label,
        binding=Withdraw(constraint_id=requirement.key),
    )


def _keeping(requirement: Constraint) -> TypedOption:
    label = f"Keep {requirement.requested_value}"[:_LABEL_LIMIT]
    return TypedOption(
        id=option_id(label),
        label=label,
        binding=Keep(constraint_id=requirement.key),
    )


def requirement_choices(requirements: Sequence[Constraint]) -> dict[str, TypedOption]:
    """The drop and the keep option of each requirement, by label."""
    return {
        option.label: option
        for requirement in requirements
        for option in (_withdrawal(requirement), _keeping(requirement))
    }


def _names(question: OpenQuestion, requirement: Constraint) -> bool:
    """Whether a question with no option carries every word of the requirement."""
    held = set(words_of(question.question))
    wanted = words_of(requirement.requested_value)
    return not question.options and all(word in held for word in wanted)


def with_withdrawals(
    questions: Sequence[OpenQuestion], unmet: Sequence[Constraint]
) -> list[OpenQuestion]:
    """The questions, with an option to withdraw each requirement no search states.

    A question on the requirement's dimension gains the option; an optionless
    question naming it, or a new question, offers to drop it or keep it. An
    optionless question keeps its own prompt, so an answer in the researcher's
    words, such as a substitute it offers, still reaches the thread."""
    asked = list(questions)
    for requirement in unmet:
        option = _withdrawal(requirement)
        about = next((i for i, q in enumerate(asked) if _names(q, requirement)), None)
        if about is not None:
            asked[about] = asked[about].model_copy(
                update={"options": [option, _keeping(requirement)]}
            )
            continue
        at = next(
            (
                i
                for i, q in enumerate(asked)
                if requirement.kind is not ConstraintKind.OTHER
                and q.dimension is requirement.kind
                and len(q.options) < _OPTIONS_LIMIT
            ),
            None,
        )
        if at is None:
            asked.append(
                OpenQuestion(
                    question=(
                        f"No search on this site states "
                        f"{requirement.requested_value!r}. Drop it from the request?"
                    )[:_QUESTION_LIMIT],
                    dimension=requirement.kind,
                    options=[option, _keeping(requirement)],
                )
            )
        elif all(o.id != option.id for o in asked[at].options):
            asked[at] = asked[at].model_copy(
                update={"options": [*asked[at].options, option]}
            )
    return asked


def with_refusals(
    questions: Sequence[OpenQuestion], refused: Sequence[tuple[Constraint, str]]
) -> list[OpenQuestion]:
    """The questions, with one per requirement whose search the site failed to
    run, offering to keep it for a later try or to drop it."""
    return [
        *questions,
        *(
            OpenQuestion(
                question=(
                    f"The site failed to run {search}. Keep "
                    f"{requirement.requested_value!r} to try again later, or drop it?"
                )[:_QUESTION_LIMIT],
                dimension=requirement.kind,
                options=[_keeping(requirement), _withdrawal(requirement)],
            )
            for requirement, search in refused
        ),
    ]


def unanswered_questions(
    questions: Sequence[OpenQuestion], *, answered: Sequence[str] = ()
) -> list[OpenQuestion]:
    """The questions the researcher has not answered; one in ``answered`` was
    decided, so it is not asked again."""
    return [q for q in questions if q.question not in answered]


def standing_recommendations(
    questions: Sequence[OpenQuestion], stated: Sequence[Constraint]
) -> list[Constraint]:
    """The recommended values the latest message leaves standing.

    A message that states a value on a dimension replaces every recommendation
    on it, so the ledger never carries two answers to one question.
    """
    replaced = {c.kind for c in stated}
    offered = (q.recommendation() for q in questions)
    return [c for c in offered if c is not None and c.kind not in replaced]
