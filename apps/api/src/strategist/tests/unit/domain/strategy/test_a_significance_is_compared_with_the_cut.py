from __future__ import annotations

import pytest

from strategist.domain.requirement_checks import grounded_check
from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    SignificanceValue,
    Statistic,
    is_blocking,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from strategist.tests.unit.domain.strategy._analysis import analysed, binding
from strategist.tests.unit.domain.strategy._linked_values import linked, requirement


def _stated(at_most: float) -> Constraint:
    return requirement(
        ConstraintKind.STATISTICAL_THRESHOLD,
        SignificanceValue(statistic="p_value", at_most=at_most),
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

    assert (grounded.status, grounded_check(grounded).why_unchecked) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_value_to_compare",
    )
    assert not is_blocking(grounded)


def _asked(statistic: Statistic) -> Constraint:
    return requirement(
        ConstraintKind.STATISTICAL_THRESHOLD,
        SignificanceValue(statistic=statistic, at_most=0.05),
    )


@pytest.mark.parametrize(
    ("statistic", "param", "shown"),
    [
        ("p_value", "pValue", "P-Value"),
        ("unspecified", "pValue", "P-Value"),
        ("fdr", "threshold", "FDR"),
        ("adjusted_p", "padj", "Adjusted p-value"),
    ],
)
def test_a_statistic_the_parameter_names_alike_is_grounded(
    statistic: Statistic, param: str, shown: str
) -> None:
    held = _asked(statistic)

    grounded = _against(
        held, linked(held, {param: "0.05"}, param, shown={param: shown})
    )

    assert grounded.status is ConstraintStatus.GROUNDED


def test_another_statistic_than_the_parameter_names_fails_its_check() -> None:
    held = _asked("fdr")

    grounded = _against(
        held, linked(held, {"pValue": "0.05"}, "pValue", shown={"pValue": "P-Value"})
    )

    assert (grounded.status, grounded.note, grounded_check(grounded).status) == (
        ConstraintStatus.SUBSTITUTED,
        "asked fdr <= 0.05, pValue holds a p_value cut of 0.05",
        "fail",
    )


def test_a_parameter_that_names_no_statistic_compares_the_cut_alone() -> None:
    held = _asked("fdr")

    grounded = _against(held, linked(held, {"cutoff": "0.05"}, "cutoff"))

    assert grounded.status is ConstraintStatus.GROUNDED
