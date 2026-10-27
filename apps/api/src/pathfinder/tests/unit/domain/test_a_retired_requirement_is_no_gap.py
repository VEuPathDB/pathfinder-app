"""A requirement the researcher withdrew or replaced yields no gap."""

from __future__ import annotations

import pytest

from pathfinder.domain.caveats import RequirementGap, WordGap, check_gaps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    Lifecycle,
    OpenLifecycle,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)


def _requirement(value: str, lifecycle: Lifecycle) -> GroundedConstraint:
    return GroundedConstraint(
        constraint=Constraint(
            kind=ConstraintKind.OTHER,
            requested_value=value,
            label=value,
            source=ConstraintSource.USER_EXPLICIT,
        ),
        status=ConstraintStatus.GROUNDED,
        lifecycle=lifecycle,
    )


@pytest.mark.parametrize(
    "lifecycle",
    [WithdrawnLifecycle(turn_id="t2"), ReplacedLifecycle(by="other:secreted")],
)
def test_a_retired_requirement_yields_no_gap(lifecycle: Lifecycle) -> None:
    gaps = check_gaps(
        words=["exported"],
        unstated=["exported"],
        requirements=[_requirement("exported", lifecycle)],
    )

    assert gaps == []


def test_an_open_requirement_leaves_the_word_gap() -> None:
    gaps = check_gaps(
        words=["exported"], requirements=[_requirement("exported", OpenLifecycle())]
    )

    assert gaps == [WordGap(word="exported")]


def test_a_requirement_no_search_states_is_one_gap_beside_its_word() -> None:
    gaps = check_gaps(
        words=["exported"],
        unstated=["exported", "secreted"],
        requirements=[_requirement("exported", OpenLifecycle())],
    )

    assert gaps == [WordGap(word="exported"), RequirementGap(text="secreted")]


def test_a_requirement_is_keyed_by_its_dimension_and_value() -> None:
    held = _requirement("exported", OpenLifecycle()).constraint

    assert held.key == "other:exported"


def test_a_lifecycle_defaults_to_open() -> None:
    grounded = GroundedConstraint(
        constraint=Constraint(
            kind=ConstraintKind.OTHER, requested_value="x", label="x"
        ),
        status=ConstraintStatus.PROVISIONAL,
    )

    assert (grounded.lifecycle, grounded.retired) == (OpenLifecycle(), False)
