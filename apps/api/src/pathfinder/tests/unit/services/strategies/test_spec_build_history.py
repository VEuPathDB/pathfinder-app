"""Rebuilding from the spec must be undoable.

``build_strategy_from_spec`` clears the graph and rewrites it from the
OperationalSpec. The Lead is told to call it once per ready spec, but it may
legitimately rebuild when the user changes the goal - and by then the
researcher may have hand-corrected a parameter in the editor. Clearing without
a history entry threw that away with nothing to undo and no trace it happened.

The rebuild itself stays destructive on purpose: materializing a new spec is
what the user asked for. What it must not be is irreversible.
"""

from __future__ import annotations

from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.session import StrategyGraph

from pathfinder.services.strategies import spec_build


def _leaf(step_id: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTaxon",
        parameters={"organism": StringValue(value=organism)},
    )


def _graph_with_hand_edit() -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    graph.record_type = "transcript"
    node = _leaf("step_a", "P. vivax P01 (hand corrected)")
    graph.steps.update(flatten_tree(node))
    graph.recompute_roots()
    return graph


async def test_the_replaced_strategy_is_recoverable() -> None:
    graph = _graph_with_hand_edit()

    before = len(graph.history)
    spec_build._replace_graph_contents(
        graph, _leaf("step_new", "P. falciparum 3D7"), name=None, description=None
    )

    assert len(graph.history) == before + 1


async def test_the_history_entry_holds_the_pre_rebuild_shape() -> None:
    graph = _graph_with_hand_edit()

    spec_build._replace_graph_contents(
        graph, _leaf("step_new", "P. falciparum 3D7"), name=None, description=None
    )

    restored = graph.history[-1].strategy_ast
    assert restored is not None
    assert restored.root.id == "step_a"
    assert restored.root.parameters["organism"] == StringValue(
        value="P. vivax P01 (hand corrected)"
    )


async def test_the_new_spec_is_what_the_graph_holds_afterwards() -> None:
    graph = _graph_with_hand_edit()

    spec_build._replace_graph_contents(
        graph, _leaf("step_new", "P. falciparum 3D7"), name=None, description=None
    )

    assert sorted(graph.steps) == ["step_new"]


async def test_building_into_an_empty_graph_records_nothing_to_undo() -> None:
    """There is no prior state to lose, so no entry is warranted."""
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")

    spec_build._replace_graph_contents(
        graph, _leaf("step_new", "P. falciparum 3D7"), name=None, description=None
    )

    assert graph.history == []
