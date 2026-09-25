"""The thread's own leaves are candidates, as their steps state them."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb_mcp.separation import ThreadSearch

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.separation.thread_searches import thread_searches

_ORGANISM: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])
}
_TEXT: dict[str, ParamValue] = {"text_expression": StringValue(value="rifin")}


def test_each_leaf_is_one_search_and_a_combine_is_none() -> None:
    graph = StrategyGraph(graph_id="g1", name="Exported", site_id="plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            search_name="boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                search_name="GenesByExportPrediction", parameters=_ORGANISM
            ),
            secondary_input=StrategyStepNode(
                search_name="GenesByText", parameters=_TEXT
            ),
        )
    )
    graph.recompute_roots()

    assert thread_searches(graph) == [
        ThreadSearch(search_name="GenesByExportPrediction", parameters=_ORGANISM),
        ThreadSearch(search_name="GenesByText", parameters=_TEXT),
    ]


def test_a_thread_with_no_strategy_has_no_search() -> None:
    assert thread_searches(None) == []
