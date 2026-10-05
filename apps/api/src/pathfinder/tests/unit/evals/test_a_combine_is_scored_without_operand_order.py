"""A case's structure reads an INTERSECT or a UNION without the order of its
inputs, and a MINUS in its order."""

from __future__ import annotations

import pytest

from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GatePlan,
)
from pathfinder.evals.scoring import ObservedOutcome, score_case


def _case(structure: str) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["a request"],
        site_id="fungidb",
        assistant_id="pathfinder",
        rationale="pins a structure",
        expected=ExpectedOutcome(builds_strategy=True, structure=structure),
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="fungidb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-10-04",
        ),
    )


@pytest.mark.parametrize("operator", ["INTERSECT", "UNION"])
def test_swapped_inputs_of_an_order_free_combine_are_the_same_structure(
    operator: str,
) -> None:
    case = _case(f"(GenesByGoTerm {operator} GenesByOrthologPattern)")
    observed = ObservedOutcome(
        built_strategy=True,
        structure=f"(GenesByOrthologPattern {operator} GenesByGoTerm)",
    )

    assert score_case(case, observed).differences == []


def test_swapped_inputs_nested_under_a_minus_are_the_same_structure() -> None:
    case = _case("((GenesByInterproDomain INTERSECT GenesByText) MINUS GenesByTaxon)")
    observed = ObservedOutcome(
        built_strategy=True,
        structure="((GenesByText INTERSECT GenesByInterproDomain) MINUS GenesByTaxon)",
    )

    assert score_case(case, observed).differences == []


def test_swapped_inputs_of_a_minus_are_another_structure() -> None:
    case = _case("(GenesByText MINUS GenesByTransmembraneDomains)")
    observed = ObservedOutcome(
        built_strategy=True, structure="(GenesByTransmembraneDomains MINUS GenesByText)"
    )

    assert [d.field for d in score_case(case, observed).differences] == ["structure"]
