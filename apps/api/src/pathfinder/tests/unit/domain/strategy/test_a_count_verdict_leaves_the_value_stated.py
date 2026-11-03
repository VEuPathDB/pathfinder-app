from __future__ import annotations

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue, param_value_from_raw
from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    CountValue,
    GroundedConstraint,
    PropertyValue,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import (
    new_value_contradiction,
    spec_stated_values,
)
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.domain.strategy._linked_values import linked, requirement

_STEP = "c_weight"
_PARAM = "weight"


def _range(low: float, high: float) -> ParamValue:
    return param_value_from_raw({"min": low, "max": high}, "number-range")


def _count(source: ConstraintSource = ConstraintSource.USER_EXPLICIT) -> Constraint:
    return requirement(
        ConstraintKind.COUNT, CountValue(feature="weight", op="<", value=30)
    ).model_copy(update={"source": source})


def _refusal(held: Constraint, value: ParamValue, written: ParamValue) -> str:
    spec = OperationalSpec(
        goal="g",
        constraints=[held],
        criteria=[
            Criterion(
                id=_STEP,
                text="under 30 kDa",
                search_name="GenesByMolecularWeight",
                answers=[RequirementLink(requirement=held.id, param=_PARAM)],
                resolved_params=bound({_PARAM: value}),
            )
        ],
    )
    graph = StrategyGraph("g1", "w", "plasmodb")
    add_step_to_graph(
        graph,
        StrategyStep(
            id=_STEP,
            kind=StepKind.SEARCH,
            search_name="GenesByMolecularWeight",
            parameters={_PARAM: written},
        ),
    )
    refused = new_value_contradiction(
        stated=spec_stated_values(spec), graph=graph, before={}
    )
    return refused or ""


@pytest.mark.parametrize(
    ("value", "written"),
    [
        (StringValue(value="30000"), StringValue(value="40000")),
        (_range(1000, 30000), _range(1000, 40000)),
    ],
    ids=["power-of-ten-scalar", "range"],
)
def test_a_rewrite_of_a_count_linked_value_is_refused(
    value: ParamValue, written: ParamValue
) -> None:
    refusal = _refusal(_count(), value, written)

    assert refusal.count(_PARAM) >= 1


def test_the_same_value_written_again_is_not_refused() -> None:
    assert _refusal(_count(), _range(1, 30), _range(1, 30)) == ""


def test_a_count_no_researcher_stated_guards_nothing() -> None:
    held = _count(ConstraintSource.ASSUMED)

    assert _refusal(held, _range(1, 30), _range(1, 40)) == ""


def test_a_property_linked_to_a_range_guards_nothing() -> None:
    held = requirement(ConstraintKind.PROPERTY, PropertyValue(phrase="small"))

    assert _refusal(held, _range(1, 30), _range(1, 40)) == ""


def _grounded(values: dict[str, str], *params: str) -> GroundedConstraint:
    held = _count()
    [grounded] = ground_against_spec(
        [held],
        OperationalSpec(goal="g", criteria=[linked(held, values, *params)]),
    )
    return grounded


@pytest.mark.parametrize(
    ("first", "second", "off"),
    [("30000", "50000", "b"), ("50000", "30000", "a")],
    ids=["scale-first", "miss-first"],
)
def test_a_real_miss_fails_beside_a_scale_difference(
    first: str, second: str, off: str
) -> None:
    grounded = _grounded({"a": first, "b": second}, "a", "b")

    assert (grounded.status, grounded.realized_param) == (
        ConstraintStatus.SUBSTITUTED,
        off,
    )
    assert grounded_check(grounded).status == "fail"


def test_two_scale_differences_are_not_verified_and_name_both() -> None:
    grounded = _grounded({"a": "30000", "b": "3000"}, "a", "b")

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.NOT_VERIFIED,
        (
            "asked weight < 30, a holds 30000, b holds 3000: each differs from the "
            "stated number by a power of ten and nothing typed states their units"
        ),
    )


def test_a_scale_difference_beside_a_met_reading_is_not_verified() -> None:
    grounded = _grounded({"a": "30000", "b": "30"}, "a", "b")

    assert grounded.status is ConstraintStatus.NOT_VERIFIED


@pytest.mark.parametrize("count", [300, 50])
def test_an_unmet_step_count_beside_a_scale_difference_fails(count: int) -> None:
    held = _count()
    criterion = Criterion(
        id=_STEP,
        text="few",
        search_name="ASearch",
        result_count=count,
        answers=[
            RequirementLink(requirement=held.id, param=_PARAM),
            RequirementLink(requirement=held.id, result_size=True),
        ],
        resolved_params=bound({_PARAM: StringValue(value="30000")}),
    )

    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=[criterion])
    )

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.SUBSTITUTED,
        f"asked weight < 30, the step returns {count}",
    )
