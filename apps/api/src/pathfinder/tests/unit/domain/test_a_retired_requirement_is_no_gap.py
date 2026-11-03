"""A requirement the researcher withdrew or replaced yields no gap, by its id."""

from __future__ import annotations

from pathfinder.domain.caveats import RequirementGap, WordGap, check_gaps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    OpenLifecycle,
)


def _requirement(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.UNTYPED,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_EXPORTED = _requirement("exported")
_SECRETED = _requirement("secreted")


def _word(requirement: Constraint) -> WordGap:
    return WordGap(word=requirement.requested_value, requirement=requirement.id)


def test_a_retired_requirement_yields_no_gap() -> None:
    gaps = check_gaps(
        words=[_word(_EXPORTED)], unstated=[_EXPORTED], retired={_EXPORTED.id}
    )

    assert gaps == []


def test_a_retired_requirement_of_the_same_words_leaves_the_held_one() -> None:
    """Two requirements share their words; only the retired id is no gap."""
    again = _requirement("exported")

    gaps = check_gaps(words=[_word(_EXPORTED), _word(again)], retired={again.id})

    assert gaps == [_word(_EXPORTED)]


def test_an_open_requirement_leaves_the_word_gap() -> None:
    assert check_gaps(words=[_word(_EXPORTED)]) == [_word(_EXPORTED)]


def test_a_requirement_no_search_states_is_one_gap_beside_its_word() -> None:
    gaps = check_gaps(words=[_word(_EXPORTED)], unstated=[_EXPORTED, _SECRETED])

    assert gaps == [
        _word(_EXPORTED),
        RequirementGap(text="secreted", requirement=_SECRETED.id),
    ]


def test_a_lifecycle_defaults_to_open() -> None:
    grounded = GroundedConstraint(
        constraint=Constraint(
            kind=ConstraintKind.UNTYPED, requested_value="x", label="x"
        ),
        status=ConstraintStatus.PROVISIONAL,
    )

    assert (grounded.lifecycle, grounded.retired) == (OpenLifecycle(), False)
