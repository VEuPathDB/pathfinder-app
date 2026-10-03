"""What the assistant asks the researcher: a question, the value it
recommends, and the options it offers, each typed by what answering it binds."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import ConfigDict, Discriminator, Field, model_validator
from veupathdb.domain.parameters import to_wire
from veupathdb.model import CamelModel

from pathfinder.domain.log2_scale import fold_label, on_scale, scale_of
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.words import words_of

_QUESTION_LIMIT = 300
_LABEL_LIMIT = 120
_OPTIONS_LIMIT = 8


class SetValues(CamelModel):
    """An option that binds these wire values on one criterion."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["set_values"] = "set_values"
    criterion_id: str
    params: dict[str, str] = Field(min_length=1)


class Withdraw(CamelModel):
    """An option that withdraws one requirement, named by its key."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["withdraw"] = "withdraw"
    constraint_id: str


class Keep(CamelModel):
    """An option that keeps one requirement as the thread holds it, by its key."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["keep"] = "keep"
    constraint_id: str


OptionBinding = Annotated[SetValues | Withdraw | Keep, Discriminator("kind")]


class TypedOption(CamelModel):
    """One option a question card offers, and what answering it binds."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    binding: OptionBinding


def _option_id(label: str) -> str:
    """The option's id: the words of its label, joined by hyphens."""
    return "-".join(words_of(label)) or label


def _by_id(labels: Sequence[str]) -> dict[str, str]:
    """Each label under its id; a label whose id an earlier one holds is dropped."""
    found: dict[str, str] = {}
    for label in labels:
        if label:
            found.setdefault(_option_id(label), label)
    return found


class _Question(CamelModel):
    """What a question asks, the dimension it decides and the value it recommends."""

    question: str = Field(min_length=1, max_length=_QUESTION_LIMIT)
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
        _refuse_a_single_option(self.question, [o.label for o in self.options])
        ids = [option.id for option in self.options]
        if len(ids) != len(set(ids)):
            msg = f"the question offers the option ids {ids} more than once"
            raise ValueError(msg)
        bound = [_binding_key(option) for option in self.options]
        if len(bound) != len(set(bound)):
            labels = [option.label for option in self.options]
            msg = (
                f"the options {labels} of {self.question!r} bind the same values, "
                f"so they are one option and the question offers no choice"
            )
            raise ValueError(msg)
        return self


def _binding_key(option: TypedOption) -> tuple[str, ...]:
    """What answering the option binds."""
    match option.binding:
        case SetValues(criterion_id=criterion_id, params=params):
            return (
                "set_values",
                criterion_id,
                *sorted(f"{k}={v}" for k, v in params.items()),
            )
        case Withdraw(constraint_id=key) | Keep(constraint_id=key):
            return (option.binding.kind, key)


def _refuse_a_single_option(question: str, labels: Sequence[str]) -> None:
    """A question that offers options offers a choice between two at least."""
    if len(labels) != 1:
        return
    msg = (
        f"the question {question!r} offers one option, {labels[0]!r}, which is no "
        f"choice: offer at least two values that each change something, or no "
        f"options for an answer in the researcher's words"
    )
    raise ValueError(msg)


class AskedQuestion(_Question):
    """A question as a model writes it: the labels of the options it offers.

    A label binds no value and is never a requirement, so the typed question
    offers none and is answered in the researcher's words.
    """

    options: list[str] = Field(default_factory=list, max_length=_OPTIONS_LIMIT)

    @model_validator(mode="after")
    def _offers_a_choice(self) -> AskedQuestion:
        _refuse_a_single_option(self.question, list(_by_id(self.options).values()))
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
        for option_id, value in _by_id(self._offered(criterion)).items():
            for reading in _readings(criterion, self.param_name, value):
                by_wire.setdefault(
                    _term_of(criterion, self.param_name, reading),
                    option_id if reading == value else _option_id(reading),
                )
        return by_wire

    def offers_a_choice(self, criterion: Criterion | None) -> bool:
        """Whether the offered values bind two values at least, or none.

        A value and the site's label of it bind one term, so two such
        options are one.
        """
        return not self.names_a_slot or len(self._by_wire(criterion)) != 1

    def typed(
        self, criterion: Criterion | None = None, *, noun: str = "record"
    ) -> OpenQuestion:
        """The question with one option per value an offered value binds.

        ``criterion`` is the one the question sets, which names the parameter
        and holds the counts measured at the offered values; ``noun`` is what
        the site counts the record type in.
        """
        if not self.names_a_slot:
            return super().typed()
        by_wire = self._by_wire(criterion)
        return OpenQuestion(
            question=self.question,
            dimension=self.dimension,
            recommended_value=self.recommended_value,
            options=[
                TypedOption(
                    id=option_id,
                    label=option_label(criterion, self.param_name, wire, noun=noun),
                    binding=SetValues(
                        criterion_id=self.criterion_id,
                        params={self.param_name: wire},
                    ),
                )
                for wire, option_id in by_wire.items()
            ],
        )


def _readings(criterion: Criterion | None, param: str, value: str) -> list[str]:
    """The values an offered value binds. A positive number offered for a
    parameter on the log2 scale is read as a fold and as a log2 value, since
    the researcher may mean either."""
    display = "" if criterion is None else criterion.display_name_of(param)
    if scale_of(display) != "log2":
        return [value]
    try:
        number = float(value)
    except ValueError:
        return [value]
    if number <= 0:
        return [value]
    return list(dict.fromkeys([f"{on_scale(number, 'fold', 'log2'):g}", value]))


def _label_of(criterion: Criterion, param: str, term: str) -> str:
    """The label the site gave for a vocabulary term, else the term."""
    return next(
        (
            m.label
            for m in criterion.measurements
            if m.kind == "vocabulary_label" and m.param == param and m.reading == term
        ),
        term,
    )


def _term_of(criterion: Criterion | None, param: str, value: str) -> str:
    """The vocabulary term an offered value names: a label the site gave for a
    term of the parameter names that term, and any other value is the term."""
    if criterion is None:
        return value
    return next(
        (
            m.reading
            for m in criterion.measurements
            if m.kind == "vocabulary_label" and m.param == param and m.label == value
        ),
        value,
    )


def option_label(
    criterion: Criterion | None, param: str, value: str, *, noun: str
) -> str:
    """The value an option binds, named by its parameter, with its count.

    A parameter the site named for the criterion leads the value, a value on
    the log2 scale is followed by the fold it stands for, and a count the site
    returned at that value follows it, in ``noun``.
    """
    if criterion is None:
        return value
    named = criterion.param_display_names.get(param, "")
    shown = _label_of(criterion, param, value)
    fold = fold_label(named, value)
    if fold:
        shown = f"{shown} ({fold})"
    label = f"{named} {shown}" if named else shown
    count = _count_at(criterion, param, value)
    if count is None:
        return label
    return f"{label}: {count} {noun}" if count == 1 else f"{label}: {count} {noun}s"


def _count_at(criterion: Criterion, param: str, value: str) -> int | None:
    """The count the site returned with the parameter at this wire value.

    The criterion's own count is measured at the value it binds; a measurement
    is measured at the reading it records.
    """
    held = criterion.resolved_params.get(param)
    if held is not None and to_wire(held.value) == value:
        return criterion.result_count
    return next(
        (
            m.count
            for m in criterion.measurements
            if m.param == param and m.reading == value and m.count is not None
        ),
        None,
    )


def _withdrawal(requirement: Constraint) -> TypedOption:
    label = f"Drop {requirement.requested_value}"[:_LABEL_LIMIT]
    return TypedOption(
        id=_option_id(label),
        label=label,
        binding=Withdraw(constraint_id=requirement.key),
    )


def _keeping(requirement: Constraint) -> TypedOption:
    label = f"Keep {requirement.requested_value}"[:_LABEL_LIMIT]
    return TypedOption(
        id=_option_id(label),
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
