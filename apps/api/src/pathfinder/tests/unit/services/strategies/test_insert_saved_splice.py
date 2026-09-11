"""The saved-strategy splice wraps the target step in a new combine."""

from __future__ import annotations

from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import walk

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.insert_saved import _build_new_root


def _leaf(step_id: str, term: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByGoTerm",
        parameters={"go_term": StringValue(value=term)},
    )


def _graph(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph("graph_1", "Kinases", "plasmodb")
    graph.steps = flatten_tree(root)
    graph.record_type = "transcript"
    graph.recompute_roots()
    return graph


def _saved() -> StrategyStepNode:
    return _leaf("saved_leaf", "GO:0005515")


def test_splicing_at_the_root_makes_the_new_combine_the_root() -> None:
    graph = _graph(
        StrategyStepNode(
            id="step_combine",
            search_name="__combine__",
            operator=CombineOp.UNION,
            primary_input=_leaf("step_a", "GO:0004672"),
            secondary_input=_leaf("step_b", "GO:0016301"),
        ),
    )

    new_root, combine_id = _build_new_root(
        graph=graph,
        target_step_id="step_combine",
        cloned_secondary=_saved(),
        operator=CombineOp.INTERSECT,
        expanded_strategy_id=7777,
        expanded_name="Binding genes",
    )

    assert new_root.id == combine_id
    assert graph.steps[combine_id].primary_input_id == "step_combine"
    assert [node.id for node in walk(new_root)] == [
        "step_a",
        "step_b",
        "step_combine",
        "saved_leaf",
        combine_id,
    ]


def test_splicing_below_the_root_rewires_only_the_parent_slot() -> None:
    graph = _graph(
        StrategyStepNode(
            id="step_root",
            search_name="__combine__",
            operator=CombineOp.UNION,
            primary_input=_leaf("step_a", "GO:0004672"),
            secondary_input=_leaf("step_b", "GO:0016301"),
        ),
    )

    new_root, combine_id = _build_new_root(
        graph=graph,
        target_step_id="step_b",
        cloned_secondary=_saved(),
        operator=CombineOp.INTERSECT,
        expanded_strategy_id=7777,
        expanded_name="Binding genes",
    )

    assert new_root.id == "step_root"
    assert graph.steps["step_root"].secondary_input_id == combine_id
    assert graph.steps[combine_id].primary_input_id == "step_b"
    assert [node.id for node in walk(new_root)] == [
        "step_a",
        "step_b",
        "saved_leaf",
        combine_id,
        "step_root",
    ]
