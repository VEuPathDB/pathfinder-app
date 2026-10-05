"""A recut reads the open analysis, so the steps it can replace are the exports
whose document names that analysis's dataset: a step that exports nothing, or
an export of another dataset, is none of them."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import flatten_tree
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.tools.standalone._eda_step_guard import (
    refuse_a_recut_of_another_dataset,
)
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda.export import exports_of
from pathfinder.tests._support.eda_step_doubles import DE_DATASET, export_step

_OTHER_DATASET = "DS_0000000000"


def test_the_exports_of_a_dataset_are_the_steps_its_documents_name() -> None:
    graph = StrategyGraph(graph_id="g1", name="DE", site_id="vectorbase")
    steps = [
        export_step("step_open", DE_DATASET),
        export_step("step_other", _OTHER_DATASET),
        export_step("step_none", DE_DATASET),
    ]
    graph.steps = {k: v for step in steps for k, v in flatten_tree(step).items()}
    graph.note_analysis_kinds(
        {
            "step_open": StampedKind(
                search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE
            ),
            "step_other": StampedKind(
                search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE
            ),
            "step_none": StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.NONE),
        }
    )

    assert exports_of(graph, DE_DATASET) == ["step_open"]


def test_an_export_takes_no_place_of_an_export_of_another_dataset() -> None:
    graph = StrategyGraph(graph_id="g1", name="DE", site_id="vectorbase")
    graph.steps = {
        **flatten_tree(export_step("step_open", DE_DATASET)),
        **flatten_tree(export_step("step_other", _OTHER_DATASET)),
    }
    graph.note_analysis_kinds(
        {
            step_id: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
            for step_id in graph.steps
        }
    )
    refuse_a_recut_of_another_dataset(graph, "step_open", DE_DATASET)

    with pytest.raises(ModelRetry) as refused:
        refuse_a_recut_of_another_dataset(graph, "step_other", DE_DATASET)

    assert refused.value.message == (
        f"step_other exports an analysis of dataset {_OTHER_DATASET}, and the open "
        f"analysis is on dataset {DE_DATASET}: an export reads the open analysis, so "
        "it cannot take that step's place. Open the analysis on "
        f"{_OTHER_DATASET} to recut it, or name a step this analysis exports."
    )
