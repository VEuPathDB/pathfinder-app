from __future__ import annotations

import pytest
from veupathdb.domain.parameters import param_value_from_raw

from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintStatus,
    CountOp,
    CountValue,
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
from pathfinder.tests.unit.domain.strategy._linked_values import requirement


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


@pytest.mark.parametrize(("op", "value"), [("<=", 50), (">=", 1)])
def test_a_count_on_a_range_reads_the_end_of_its_side(
    op: CountOp, value: float
) -> None:
    assert _status(op, value) is ConstraintStatus.GROUNDED


@pytest.mark.parametrize(("op", "value"), [("<=", 60), (">=", 5)])
def test_a_count_off_the_end_of_its_side_is_substituted(
    op: CountOp, value: float
) -> None:
    assert _status(op, value) is ConstraintStatus.SUBSTITUTED


def test_an_exact_count_on_a_range_has_no_end_to_read() -> None:
    assert _status("=", 50) is ConstraintStatus.NOT_VERIFIED
