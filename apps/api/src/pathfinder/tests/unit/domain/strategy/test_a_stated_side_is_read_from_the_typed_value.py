from __future__ import annotations

import pytest
from veupathdb.domain.parameters import param_value_from_raw

from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintStatus,
    CountOp,
    CountValue,
    GroundedConstraint,
    PercentileEnd,
    PercentileValue,
    PropertyValue,
    RangeSide,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.tests.unit.domain.strategy._linked_values import linked, requirement


@pytest.mark.parametrize(
    ("op", "side"),
    [(">=", "lower"), (">", "lower"), ("<=", "upper"), ("<", "upper"), ("=", None)],
)
def test_a_count_states_the_side_of_its_operator(
    op: CountOp, side: RangeSide | None
) -> None:
    held = requirement(
        ConstraintKind.COUNT, CountValue(feature="anything", op=op, value=3)
    )

    assert held.side == side


@pytest.mark.parametrize(("end", "side"), [("top", "lower"), ("bottom", "upper")])
def test_a_percentile_states_the_side_of_its_end(
    end: PercentileEnd, side: RangeSide
) -> None:
    held = requirement(ConstraintKind.PERCENTILE, PercentileValue(end=end, share=10))

    assert held.side == side


def test_a_property_states_no_side() -> None:
    held = requirement(ConstraintKind.PROPERTY, PropertyValue(phrase="under 30 kDa"))

    assert (held.kind, held.side) == (ConstraintKind.PROPERTY, None)


def _status(op: CountOp, value: float) -> ConstraintStatus:
    held = requirement(
        ConstraintKind.COUNT, CountValue(feature="percent", op=op, value=value)
    )
    criterion = Criterion(
        id="c1",
        text="junctions",
        search_name="GenesByIntronJunctions",
        answers=[RequirementLink(requirement=held.id, param="percent_max")],
        resolved_params={
            "percent_max": BoundValue(
                value=param_value_from_raw({"min": 1, "max": 50}, "number-range"),
                source="chosen",
            )
        },
    )
    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=[criterion])
    )
    return grounded.status


@pytest.mark.parametrize(
    ("op", "value"), [("<=", 50), (">=", 1), ("<=", 60), (">=", 5), ("=", 50)]
)
def test_a_count_is_never_compared_with_the_end_of_a_range(
    op: CountOp, value: float
) -> None:
    assert _status(op, value) is ConstraintStatus.NOT_VERIFIED


def _scalar(op: CountOp, asked: float, wire: str) -> GroundedConstraint:
    held = requirement(
        ConstraintKind.COUNT, CountValue(feature="length", op=op, value=asked)
    )
    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=[linked(held, {"x": wire}, "x")])
    )
    return grounded


@pytest.mark.parametrize(
    ("asked", "wire"), [(30, "30000"), (2.5, "2500"), (2000, "2"), (5, "50")]
)
def test_a_number_a_power_of_ten_away_is_not_verified(asked: float, wire: str) -> None:
    grounded = _scalar("<", asked, wire)

    assert (grounded.status, grounded.unverified) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_value_to_compare",
    )


@pytest.mark.parametrize(
    ("asked", "wire"), [(30, "50000"), (4, "6"), (0, "5"), (5, "0"), (-5, "50")]
)
def test_any_other_number_stays_a_miss(asked: float, wire: str) -> None:
    grounded = _scalar("<", asked, wire)

    assert grounded.status is ConstraintStatus.SUBSTITUTED


def test_a_step_count_a_power_of_ten_away_stays_a_miss() -> None:
    held = requirement(
        ConstraintKind.COUNT, CountValue(feature="genes", op="<=", value=50)
    )
    criterion = Criterion(
        id="c1",
        text="few genes",
        search_name="ASearch",
        result_count=500,
        answers=[RequirementLink(requirement=held.id, result_size=True)],
    )

    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=[criterion])
    )

    assert grounded.status is ConstraintStatus.SUBSTITUTED
