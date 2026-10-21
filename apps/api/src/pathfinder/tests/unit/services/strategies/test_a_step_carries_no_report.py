"""A step on the wire carries no report configuration."""

from __future__ import annotations

from veupathdb.domain.strategy import (
    StepReport,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.tools.standalone.graph_helpers import build_step_response
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.schemas import step_response_from_strategy_ast


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_a",
        search_name="GenesByExportPrediction",
        reports=[StepReport(report_name="attributesTabular")],
    )


def test_a_step_response_names_no_report() -> None:
    graph = StrategyGraph("g1", "GPI", "plasmodb")
    graph.steps.update(flatten_tree(_leaf()))
    graph.recompute_roots()
    stored = StrategyAst(record_type="transcript", root=_leaf())

    wired = [
        build_step_response(graph, graph.steps["step_a"]).model_dump(by_alias=True),
        step_response_from_strategy_ast(stored, stored.root).model_dump(by_alias=True),
    ]

    assert ["reports" in w for w in wired] == [False, False]
