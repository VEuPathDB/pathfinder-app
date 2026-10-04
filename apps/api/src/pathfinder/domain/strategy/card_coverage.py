"""The stated requirements a proposal card leaves with no change, no question
and no step of the strategy that holds them."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from veupathdb.domain.parameters import to_wire

from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    GENE_RECORD_NOUNS,
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    record_noun,
    states_the_content,
)
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.message_reading import message_states_constraint
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec

# The dimensions the grounding reads from the searches and values of the spec.
_GROUNDED_KINDS = frozenset(
    {
        ConstraintKind.DATA_TYPE,
        ConstraintKind.STATISTICAL_THRESHOLD,
        ConstraintKind.FOLD_CHANGE,
        ConstraintKind.PERCENTILE,
    }
)
_NO_MARKS = DataMarks()


def _criterion_words(criterion: Criterion) -> str:
    """The criterion's own words and every value its step carries."""
    return " ".join(
        [criterion.text, *(to_wire(v) for v in criterion.param_values.values())]
    )


def _counts_the_records(spec: OperationalSpec, value: str) -> bool:
    held = set(record_noun(spec.record_type).split())
    asked = set(record_noun(value).split())
    return held == asked or (held | asked) <= GENE_RECORD_NOUNS


def _name_each_other(term: str, value: str) -> bool:
    """Whether one of the two carries every content word of the other."""
    return states_the_content(term, value) or states_the_content(value, term)


def held_by_the_spec(
    requirement: Constraint,
    spec: OperationalSpec | None,
    *,
    marks: DataMarks = _NO_MARKS,
) -> bool:
    """Whether the strategy already holds the requirement.

    A record type is held when the spec counts the same records, and an organism
    when the scope or a step's values name it. A data type, a threshold, a fold
    change or a percentile is held when the spec grounds it. Any value is held
    when a criterion's words or values state it.
    """
    if spec is None:
        return False
    if requirement.kind is ConstraintKind.RECORD_TYPE:
        return _counts_the_records(spec, requirement.requested_value)
    texts = [_criterion_words(c) for c in spec.criteria]
    if requirement.kind is ConstraintKind.ORGANISM:
        texts.append(spec.organism_scope or "")
        return any(message_states_constraint(t, requirement) for t in texts if t)
    if requirement.kind in _GROUNDED_KINDS:
        [grounded] = ground_against_spec([requirement], spec, marks=marks)
        if grounded.status is ConstraintStatus.GROUNDED:
            return True
    return any(states_the_content(t, requirement.requested_value) for t in texts)


def uncovered_requirements(
    stated: Sequence[Constraint],
    *,
    named: Collection[str],
    held: Sequence[Constraint],
    spec: OperationalSpec | None,
    marks: DataMarks = _NO_MARKS,
) -> list[Constraint]:
    """The stated requirements a card does not cover.

    A card covers a requirement it names by key, and one the strategy holds. It
    covers a combination when it covers each term: a term is covered when a
    covered requirement or a criterion of the spec states it.
    """
    covered = [
        c
        for c in held
        if c.key in named
        or (
            c.kind is not ConstraintKind.COMBINATION
            and held_by_the_spec(c, spec, marks=marks)
        )
    ]
    criteria = [] if spec is None else [_criterion_words(c) for c in spec.criteria]

    def _term_covered(term: str) -> bool:
        return any(_name_each_other(term, c.requested_value) for c in covered) or any(
            states_the_content(text, term) for text in criteria
        )

    def _covers(requirement: Constraint) -> bool:
        if requirement.key in named:
            return True
        if requirement.kind is not ConstraintKind.COMBINATION:
            return held_by_the_spec(requirement, spec, marks=marks)
        request = CombinationRequest.parse(requirement.requested_value)
        return request is not None and all(_term_covered(t) for t in request.terms)

    return [c for c in stated if not _covers(c)]
