"""The gate the last turn stopped on, and the count the strategy's root holds."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GateEnd
from pathfinder.evals.scoring import ObservedOutcome, root_count, score_case


def _case(ends_on: GateEnd | None) -> EvalCase:
    return EvalCase(
        name="uat-n5-plasmodb",
        turns=[
            "Delete the intersection step but keep both searches exactly as they are."
        ],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the card",
        expected=ExpectedOutcome(builds_strategy=None, ends_on=ends_on),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="uat/flows-strategy-exceptions.md#n5",
            added_at="2026-09-25",
        ),
    )


def test_a_card_that_did_not_come_is_a_difference() -> None:
    observed = ObservedOutcome(built_strategy=True, ends_on="none")

    differences = score_case(_case("approval"), observed).differences

    assert [(d.field, d.expected, d.actual) for d in differences] == [
        ("endsOn", "approval", "none"),
    ]


def test_the_card_that_came_passes() -> None:
    observed = ObservedOutcome(built_strategy=True, ends_on="approval")

    assert score_case(_case("approval"), observed).passed is True


def test_a_case_that_names_no_gate_reads_none() -> None:
    observed = ObservedOutcome(built_strategy=True, ends_on="proposal")

    assert score_case(_case(None), observed).passed is True


def _intersect(counts: dict[str, int]) -> StrategyAst:
    left = StrategyStepNode(id="sp", search_name="GenesWithSignalPeptide")
    right = StrategyStepNode(id="tm", search_name="GenesByTransmembraneDomains")
    root = StrategyStepNode(
        id="root",
        search_name="__combine__",
        primary_input=left,
        secondary_input=right,
        operator=CombineOp.INTERSECT,
    )
    return StrategyAst(record_type="transcript", root=root, step_counts=counts)


def test_the_root_count_is_the_count_of_the_root_step() -> None:
    counted = _intersect({"sp": 479, "tm": 840, "root": 116})

    assert root_count(counted) == 116


def test_a_root_the_site_did_not_count_has_no_count_and_an_empty_root_has_zero() -> (
    None
):
    counts = (
        root_count(_intersect({"sp": 479, "tm": 840})),
        root_count(_intersect({"sp": 479, "tm": 840, "root": 0})),
    )

    assert counts == (None, 0)
