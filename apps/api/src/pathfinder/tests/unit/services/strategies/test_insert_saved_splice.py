"""The saved-strategy splice wraps the target step in a new combine."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree, walk

from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import insert_saved
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.insert_saved import (
    _build_new_root,
    insert_saved_into_conversation,
)


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


_REFUSAL = "the criterion 'binding' states go_term = 'GO:0005515'"


class _Cloned:
    def __init__(self, root: StrategyStepNode) -> None:
        self.root = root
        self.name = "Binding genes"
        self.record_type = "transcript"


async def test_a_build_the_spec_refuses_leaves_the_graph_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The splice wires a combine before the build runs, so a refusal undoes it."""
    graph = _graph(
        StrategyStepNode(
            id="step_combine",
            search_name="__combine__",
            operator=CombineOp.UNION,
            primary_input=_leaf("step_a", "GO:0004672"),
            secondary_input=_leaf("step_b", "GO:0016301"),
        ),
    )
    before = sorted(graph.steps)
    session = StrategySession(site_id="plasmodb")
    session.graph = graph

    async def _clone(*_args: Any, **_kwargs: Any) -> _Cloned:
        return _Cloned(_saved())

    async def _refuse(**_kwargs: Any) -> None:
        raise ApplyError(_REFUSAL)

    monkeypatch.setattr(insert_saved, "clone_saved_strategy", _clone)
    monkeypatch.setattr(insert_saved, "build_strategy_from_spec", _refuse)

    with pytest.raises(ApplyError):
        await insert_saved_into_conversation(
            deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
            target_step_id="step_combine",
            saved_wdk_strategy_id=7777,
            operator=CombineOp.INTERSECT,
        )

    assert sorted(graph.steps) == before
    assert sorted(graph.roots) == ["step_combine"]
