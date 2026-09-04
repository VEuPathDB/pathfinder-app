from __future__ import annotations

import pytest

from pathfinder.domain.parameters.values import (
    MultiPickValue,
    SinglePickValue,
    StringValue,
)
from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.integrations.veupathdb.factory import get_results_api
from pathfinder.services.control_tests import run_step_control_tests
from pathfinder.services.enrichment.service import EnrichmentService
from pathfinder.tests.integration.strategies.conftest import BuildAndRead, RoundTrip

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORGANISM = "Plasmodium falciparum 3D7"


def _text_leaf(expr: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="leaf",
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value=expr),
            "text_fields": MultiPickValue(values=["product"]),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=[_ORGANISM]),
        },
    )


def _go_kinase_leaf() -> StrategyStepNode:
    """GO:0004672 protein kinase activity — the curated kinase truth set."""
    return StrategyStepNode(
        id="go_kinases",
        search_name="GenesByGoTerm",
        parameters={
            "organism": MultiPickValue(values=[_ORGANISM]),
            "go_term_evidence": MultiPickValue(values=["Curated", "Computed"]),
            "go_term_slim": SinglePickValue(value="No"),
            "go_typeahead": MultiPickValue(values=["GO:0004672"]),
            "go_term": StringValue(value="GO:0004672"),
        },
    )


async def _step_ids(rt: RoundTrip) -> tuple[int, set[str]]:
    assert rt.decoded.wdk_step_ids
    step = next(iter(rt.decoded.wdk_step_ids.values()))
    answer = await get_results_api("plasmodb").get_step_preview(step, limit=50000)
    return step, {r.display_name for r in answer.records}


async def test_go_process_enrichment_returns_real_kinase_terms(
    wdk_builder: BuildAndRead,
) -> None:
    rt = await wdk_builder(_text_leaf("kinase"))
    assert rt.decoded.wdk_step_ids
    wdk_step_id = next(iter(rt.decoded.wdk_step_ids.values()))

    results, errors = await EnrichmentService().run_batch(
        site_id="plasmodb",
        analysis_types=["go_process"],
        step_id=wdk_step_id,
        search_name="GenesByText",
        record_type="transcript",
        parameters=dict(_text_leaf("kinase").parameters),
    )

    assert errors == [], errors
    assert len(results) == 1
    go = results[0]
    assert go.analysis_type == "go_process"
    assert go.total_genes_analyzed >= 100
    assert len(go.terms) >= 5
    for term in go.terms:
        assert term.term_id.startswith("GO:")
        assert term.term_name
        assert 0.0 <= term.p_value <= 1.0
        assert all(g.startswith("PF3D7") for g in term.genes)
    # The kinase set enriches strongly for phosphorylation.
    assert any("phosphorylat" in t.term_name.lower() for t in go.terms)


async def test_control_tests_recall_and_fpr_on_curated_kinase_set(
    wdk_builder: BuildAndRead,
) -> None:
    kinase_step, _ = await _step_ids(await wdk_builder(_text_leaf("kinase")))
    _, go_kinases = await _step_ids(await wdk_builder(_go_kinase_leaf()))
    _, phosphatases = await _step_ids(await wdk_builder(_text_leaf("phosphatase")))

    assert len(go_kinases) >= 90, len(go_kinases)
    assert len(phosphatases) >= 40, len(phosphatases)

    result = await run_step_control_tests(
        site_id="plasmodb",
        wdk_step_id=kinase_step,
        positive_controls=sorted(go_kinases),
        negative_controls=sorted(phosphatases),
    )

    assert result.positive_controls_count == len(go_kinases)
    assert result.positive_intersection is not None
    assert result.positive_intersection >= 80
    assert result.positive_recall is not None
    assert result.positive_recall >= 0.80

    assert result.negative_controls_count == len(phosphatases)
    assert result.negative_intersection is not None
    assert result.negative_intersection <= 10
    assert result.negative_false_positive_rate is not None
    assert result.negative_false_positive_rate <= 0.20
