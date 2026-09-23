"""A build keeps no count from the tree it replaces.

The build writes a whole new tree, and a criterion id can name a step in both
of them. A count carried across describes a search the new step does not run,
and the local tree is persisted before any push, so it would reach the client
as this build's number.
"""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import spec_build
from pathfinder.services.strategies.sync_state import WDKSyncState

_KEPT_ID = "step_1"


def _leaf(step_id: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTaxon",
        parameters={"organism": StringValue(value=organism)},
    )


def _graph() -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(_leaf(_KEPT_ID, "P. vivax P01")))
    graph.recompute_roots()
    return graph


def _state() -> WDKSyncState:
    return WDKSyncState(step_counts={_KEPT_ID: 2862, "step_2": 71})


def test_a_reused_step_id_keeps_no_count() -> None:
    sync_state = _state()

    spec_build._replace_graph_contents(
        _graph(),
        _leaf(_KEPT_ID, "P. falciparum 3D7"),
        sync_state=sync_state,
        description=None,
        criterion_texts={},
    )

    assert sync_state.step_counts == {}


def test_no_count_of_the_replaced_tree_survives() -> None:
    sync_state = _state()

    spec_build._replace_graph_contents(
        _graph(),
        _leaf("step_new", "P. falciparum 3D7"),
        sync_state=sync_state,
        description=None,
        criterion_texts={},
    )

    assert sync_state.step_counts == {}
