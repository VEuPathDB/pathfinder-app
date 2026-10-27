from __future__ import annotations

import pytest

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.domain.strategy._analysis import analysed, binding


def _stated(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.STATISTICAL_THRESHOLD,
        requested_value=value,
        label="significance",
        source=ConstraintSource.USER_EXPLICIT,
    )


def _spec(significance: float) -> OperationalSpec:
    return OperationalSpec(
        goal="genes higher in 24h than in 18h",
        criteria=[analysed(bound=binding(significance=significance))],
    )


@pytest.mark.parametrize("value", ["p < 0.05", "p<.05", "5% FDR", "padj 0.050"])
def test_a_stated_cut_the_analysis_holds_is_grounded(value: str) -> None:
    [grounded] = ground_against_spec([_stated(value)], _spec(0.05))

    assert (grounded.status, grounded.realized_param, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        "significance_threshold",
        "0.05",
    )
    assert grounded_check(grounded).status == "pass"


def test_a_cut_short_of_the_stated_one_fails_its_check() -> None:
    [grounded] = ground_against_spec([_stated("p < 0.01")], _spec(0.05))

    check = grounded_check(grounded)
    assert (grounded.status, check.status, check.evidence) == (
        ConstraintStatus.SUBSTITUTED,
        "fail",
        "asked 0.01, built 0.05",
    )


def test_a_statement_of_no_one_number_is_grounded_on_the_parameter_alone() -> None:
    [grounded] = ground_against_spec([_stated("significant genes")], _spec(0.05))

    assert (grounded.status, grounded_check(grounded).status) == (
        ConstraintStatus.GROUNDED,
        "unchecked",
    )
