"""A recorded separation run becomes an offer that builds with no model in between.

The run is the tool server's own answer on plasmodb, exact mode on the seed
"PF3D7 Signal Peptide Genes"; every count asserted here is the site's.
"""

from __future__ import annotations

import math
from typing import Literal

from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb_mcp.catalog import format_param_info_typed
from veupathdb_mcp.separation import (
    SeparationNode,
    SeparationResult,
    hypergeometric_log_sf,
)

from pathfinder.domain.separation import SeparationOffer, SeparationReport
from pathfinder.domain.strategy.spec_tree import build_step_tree
from pathfinder.domain.strategy.step_rationale import ControlsRationale
from pathfinder.services.separation.offer import separation_report
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.separation import (
    ERYTHROCYTE_INVASION,
    SIGNAL_PEPTIDE,
    TASK_ID,
    recorded_separation,
)


def _report(result: SeparationResult) -> SeparationReport:
    return separation_report(result, task_id=TASK_ID, sheets={})


def _offer(result: SeparationResult) -> SeparationOffer:
    offer = _report(result).offer
    assert offer is not None
    return offer


def _shape(step: StrategyStepNode) -> object:
    if step.primary_input is None:
        return (step.search_name, step.parameters)
    assert step.secondary_input is not None
    return (step.operator, _shape(step.primary_input), _shape(step.secondary_input))


def _leaf(candidate_id: str) -> SeparationNode:
    return SeparationNode(kind="leaf", candidate_id=candidate_id)


def test_the_offer_builds_the_tree_the_run_assembled() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    measured = {m.candidate.id: m.candidate for m in result.measured}
    offer = _offer(result)

    built = build_step_tree(offer.spec)

    assert offer.spec.ready_to_build
    assert _shape(built.root) == (
        CombineOp.UNION,
        (
            CombineOp.UNION,
            ("GenesByGoTerm", measured["c4"].parameters),
            ("GenesByGoTerm", measured["c1"].parameters),
        ),
        (measured["c15"].search_name, measured["c15"].parameters),
    )
    assert [c.role for c in offer.spec.criteria] == ["seed", "seed", "seed"]


def test_a_subtracted_candidate_is_an_excluded_criterion() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    assert result.tree is not None
    minus = SeparationNode(
        kind="combine", operator=CombineOp.MINUS, inputs=[result.tree, _leaf("c18")]
    )
    offer = _offer(result.model_copy(update={"tree": minus}))

    root = build_step_tree(offer.spec).root
    roles = {c.id: c.role for c in offer.spec.criteria}

    assert (
        root.operator,
        root.secondary_input and root.secondary_input.search_name,
    ) == (
        CombineOp.MINUS,
        "GenesWithStructurePrediction",
    )
    assert roles == {"c4": "seed", "c1": "seed", "c15": "seed", "c18": "exclude"}


def _branch(
    operator: Literal[CombineOp.INTERSECT, CombineOp.MINUS], left: str, right: str
) -> SeparationNode:
    return SeparationNode(
        kind="combine", operator=operator, inputs=[_leaf(left), _leaf(right)]
    )


def test_a_subtracted_branch_builds_nested_and_keeps_back_its_right_input() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    assert result.tree is not None
    minus = SeparationNode(
        kind="combine",
        operator=CombineOp.MINUS,
        inputs=[result.tree, _branch(CombineOp.MINUS, "c18", "c5")],
    )
    offer = _offer(result.model_copy(update={"tree": minus}))

    branch = build_step_tree(offer.spec).root.secondary_input
    roles = {c.id: c.role for c in offer.spec.criteria}

    assert branch is not None
    assert (
        branch.operator,
        branch.primary_input and branch.primary_input.search_name,
        branch.secondary_input and branch.secondary_input.search_name,
    ) == (CombineOp.MINUS, "GenesWithStructurePrediction", "GenesByGoTerm")
    assert roles == {
        "c4": "seed",
        "c1": "seed",
        "c15": "seed",
        "c18": "exclude",
        "c5": "filter",
    }
    assert [c.criterion_id for c in offer.contributions] == [
        "c4",
        "c1",
        "c15",
        "c18",
        "c5",
    ]


def test_both_inputs_of_a_subtracted_intersection_are_excluded() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    assert result.tree is not None
    minus = SeparationNode(
        kind="combine",
        operator=CombineOp.MINUS,
        inputs=[result.tree, _branch(CombineOp.INTERSECT, "c18", "c5")],
    )
    offer = _offer(result.model_copy(update={"tree": minus}))

    roles = {c.id: c.role for c in offer.spec.criteria}

    assert (roles["c18"], roles["c5"]) == ("exclude", "exclude")


def test_each_criterion_states_the_counts_its_own_step_returned() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    offer = _offer(result)

    assert {c.id: c.rationale for c in offer.spec.criteria} == {
        "c4": ControlsRationale(
            task_id=str(TASK_ID),
            search_name="GenesByGoTerm",
            source="enrichment",
            basis="GO:0044217 other organism part",
            informs="recovering",
            recovered=42,
            positives=80,
            admitted=0,
            negatives=40,
            result_size=637,
        ),
        "c1": ControlsRationale(
            task_id=str(TASK_ID),
            search_name="GenesByGoTerm",
            source="enrichment",
            basis="GO:0051701 biological process involved in interaction with host",
            informs="recovering",
            recovered=38,
            positives=80,
            admitted=0,
            negatives=40,
            result_size=417,
        ),
        "c15": ControlsRationale(
            task_id=str(TASK_ID),
            search_name=(
                "GenesBySubcellularLocalization"
                "pfal3D7_subcellular_localization_Cowman_RSRC"
            ),
            source="catalog",
            basis="the site's catalog",
            informs="recovering",
            recovered=33,
            positives=80,
            admitted=0,
            negatives=40,
            result_size=316,
        ),
    }


def test_the_offer_holds_the_sites_read_and_its_enrichment() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    assert result.positive is not None
    assert result.negative is not None
    offer = _offer(result)

    assert (offer.positive.returned, offer.positive.not_returned) == (
        result.positive.recovered_ids,
        result.positive.missed_ids,
    )
    assert (offer.negative.returned, offer.negative.not_returned) == (
        result.negative.admitted_ids,
        result.negative.excluded_ids,
    )
    assert (offer.result_size, offer.separates, offer.mode) == (800, False, "exact")
    assert offer.enrichment.p_value == math.exp(hypergeometric_log_sf(50, 120, 80, 50))
    assert offer.question == (
        "Build the closest strategy found: 3 searches returning 50 of 80 "
        "positives and 0 of 40 negatives in 800 genes?"
    )


def test_each_leaf_is_read_by_what_the_tree_loses_without_it() -> None:
    offer = _offer(recorded_separation(SIGNAL_PEPTIDE))

    assert [(c.criterion_id, c.line) for c in offer.contributions] == [
        ("c4", "without it: -5 positives, 0 negatives"),
        ("c1", "without it: -6 positives, 0 negatives"),
        ("c15", "without it: -2 positives, 0 negatives"),
    ]


def test_the_report_keeps_the_ranked_measurements_and_the_skipped_counts() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE)
    report = _report(result)

    assert [m.candidate_id for m in report.measured] == [
        m.candidate.id for m in result.measured
    ]
    assert (report.informative_count, len(report.measured)) == (14, 23)
    assert report.skipped_by_reason == {
        "budget": 2,
        "unbound_required": 4,
        "wdk_refused": 2,
    }
    assert len(report.skipped_examples) == 8
    assert (report.charged_requests, report.budget) == (379, 400)
    assert report.shortfall == result.shortfall
    assert report.summary == (
        "no strategy separates the sets; closest: 50 of 80 positives, 0 of 40 "
        "negatives, 800 genes, 3 searches; 379 of 400 requests"
    )


def test_a_similar_run_offers_its_closest_tree_too() -> None:
    offer = _offer(recorded_separation(ERYTHROCYTE_INVASION))

    assert (offer.mode, offer.separates, offer.result_size) == ("similar", False, 166)
    assert [c.id for c in offer.spec.criteria] == ["c11", "c2", "c6", "c4"]


def test_a_run_that_assembled_nothing_offers_nothing() -> None:
    result = recorded_separation(SIGNAL_PEPTIDE).model_copy(
        update={
            "tree": None,
            "positive": None,
            "negative": None,
            "result_size": None,
            "shortfall": ["No measured criterion recovers any positive."],
        }
    )

    report = _report(result)

    assert (report.offer, report.shortfall) == (
        None,
        ["No measured criterion recovers any positive."],
    )
    assert report.summary == (
        "no strategy assembled; No measured criterion recovers any positive."
    )


def test_each_offered_value_is_read_on_the_published_sheet_of_its_search() -> None:
    sheet = [
        info
        for info in format_param_info_typed(
            list(suite_search("search_genes_by_text").parameters or [])
        )
        if info.is_visible
    ]

    report = separation_report(
        recorded_separation(ERYTHROCYTE_INVASION),
        task_id=TASK_ID,
        sheets={"GenesByText": sheet},
    )

    assert report.offer is not None
    [pfemp1] = [c for c in report.offer.spec.criteria if c.id == "c11"]
    fields = pfemp1.resolved_params["text_fields"]
    text = pfemp1.resolved_params["text_expression"]
    assert (
        fields.source,
        fields.display_name,
        fields.label,
        text.display_name,
        text.at_default,
        pfemp1.resolved_params["document_type"].display_name,
    ) == (
        "card",
        "Fields",
        "Product description",
        "Text term (use * as wildcard)",
        False,
        "",
    )
