from __future__ import annotations

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    SignificanceValue,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.tests.unit.domain.strategy._analysis import analysed, binding
from pathfinder.tests.unit.domain.strategy._linked_values import linked, requirement


def _stated(at_most: float) -> Constraint:
    return requirement(
        ConstraintKind.STATISTICAL_THRESHOLD,
        SignificanceValue(statistic="adjusted_p", at_most=at_most),
    )


def _against(held: Constraint, *criteria: Criterion) -> GroundedConstraint:
    [grounded] = ground_against_spec(
        [held], OperationalSpec(goal="g", criteria=list(criteria))
    )
    return grounded


def _linked_analysis(held: Constraint, significance: float) -> Criterion:
    return analysed(bound=binding(significance=significance)).model_copy(
        update={"answers": [RequirementLink(requirement=held.id)]}
    )


def test_a_cut_the_linked_analysis_holds_is_grounded() -> None:
    held = _stated(0.05)

    grounded = _against(held, _linked_analysis(held, 0.05))

    assert (grounded.status, grounded.realized_param, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        "significance_threshold",
        "0.05",
    )
    assert grounded_check(grounded).status == "pass"


def test_a_cut_short_of_the_stated_one_fails_its_check() -> None:
    held = _stated(0.01)

    grounded = _against(held, _linked_analysis(held, 0.05))

    check = grounded_check(grounded)
    assert (grounded.status, check.status, check.evidence) == (
        ConstraintStatus.SUBSTITUTED,
        "fail",
        "asked 0.01, built 0.05",
    )


def test_a_linked_parameter_holds_the_cut() -> None:
    held = _stated(0.001)

    grounded = _against(held, linked(held, {"p_value": "0.001"}, "p_value"))

    assert (grounded.status, grounded.realized_param) == (
        ConstraintStatus.GROUNDED,
        "p_value",
    )


def test_an_analysis_that_does_not_link_it_is_not_verified() -> None:
    grounded = _against(_stated(0.05), analysed(bound=binding(significance=0.05)))

    assert (grounded.status, grounded_check(grounded).status) == (
        ConstraintStatus.GROUNDED,
        "unchecked",
    )
    assert not is_blocking(grounded)
