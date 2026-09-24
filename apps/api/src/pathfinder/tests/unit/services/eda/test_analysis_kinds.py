"""A step's analysis kind, read once from the catalog by the query its search runs."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda.analysis_kinds import analysis_kinds_of
from pathfinder.services.eda.export import exported_analysis
from pathfinder.tests._support.analysis_catalog import (
    DESEQ_SEARCH,
    UNREADABLE_SEARCH,
    WGCNA_SEARCH,
    serve_the_catalog,
)
from pathfinder.tests.unit.ai.lead._analysis_thread import document

_DATASET = "DS_e973eadd57"


def eda_node(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET),
            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
        },
    )


async def test_each_step_takes_the_kind_its_query_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = serve_the_catalog(monkeypatch)
    nodes = [
        eda_node("step_deseq", DESEQ_SEARCH),
        eda_node("step_deseq_2", DESEQ_SEARCH),
        eda_node("step_subset", "GenesByEdaSubset"),
        eda_node("step_wgcna", WGCNA_SEARCH),
        StrategyStepNode(
            id="step_taxon",
            search_name="GenesByTaxon",
            parameters={"organism": NumberValue(value=1)},
        ),
    ]

    kinds = await analysis_kinds_of(
        site_id="plasmodb", record_type="transcript", nodes=nodes
    )

    assert kinds == {
        "step_deseq": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE),
        "step_deseq_2": StampedKind(
            search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE
        ),
        "step_subset": StampedKind(
            search_name="GenesByEdaSubset", kind=AnalysisKind.SUBSET
        ),
        "step_wgcna": StampedKind(search_name=WGCNA_SEARCH, kind=AnalysisKind.NONE),
    }
    assert read == [DESEQ_SEARCH, "GenesByEdaSubset", WGCNA_SEARCH]


async def test_a_search_the_catalog_cannot_read_takes_no_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_catalog(monkeypatch)

    kinds = await analysis_kinds_of(
        site_id="plasmodb",
        record_type="transcript",
        nodes=[eda_node("step_x", UNREADABLE_SEARCH)],
    )

    assert kinds == {}


async def test_a_per_dataset_deseq_step_reads_the_cut_its_plugin_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_catalog(monkeypatch)
    node = eda_node("step_deseq", DESEQ_SEARCH)
    kinds = await analysis_kinds_of(
        site_id="plasmodb", record_type="transcript", nodes=[node]
    )

    binding = exported_analysis(kinds[node.id].kind, node.parameters)

    assert binding is not None
    assert (binding.effect_size_threshold, binding.significance_threshold) == (
        1.0,
        0.05,
    )


async def test_a_wgcna_step_reads_as_no_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GenesByWGCNAModule declares the parameter and never reads it."""
    serve_the_catalog(monkeypatch)
    node = eda_node("step_wgcna", WGCNA_SEARCH)
    kinds = await analysis_kinds_of(
        site_id="plasmodb", record_type="transcript", nodes=[node]
    )

    assert (kinds, exported_analysis(kinds[node.id].kind, node.parameters)) == (
        {node.id: StampedKind(search_name=WGCNA_SEARCH, kind=AnalysisKind.NONE)},
        None,
    )
