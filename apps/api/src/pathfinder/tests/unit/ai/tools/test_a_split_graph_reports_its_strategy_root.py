"""A graph with more than one root cites the strategy's root, never a sum."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.tools.standalone import strategy_graph
from pathfinder.ai.tools.standalone.stream_parts import (
    graph_snapshot_chunk,
    strategy_meta_chunk,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_GO = "step_a1b2c3d4"
_TEXT = "step_b5c6d7e8"
_GO_WDK = 440_432_473
_TEXT_WDK = 440_432_474


def _session(*, wdk_step_tree: WDKStepTree | None) -> StrategySession:
    """Two roots, neither consuming the other, as a detaching edit leaves them."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = {
        **flatten_tree(StrategyStepNode(id=_GO, search_name="GenesByGoTerm")),
        **flatten_tree(StrategyStepNode(id=_TEXT, search_name="GenesByText")),
    }
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={_GO: _GO_WDK, _TEXT: _TEXT_WDK},
        step_counts={_GO: 1282, _TEXT: 61},
        wdk_strategy_id=330_642_473,
        wdk_step_tree=wdk_step_tree,
    )
    return session


def _one_root_session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id=_GO, search_name="GenesByGoTerm"))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={_GO: _GO_WDK},
        step_counts={_GO: 1282},
        wdk_strategy_id=330_642_473,
    )
    return session


def test_the_snapshot_cites_the_strategy_root_and_names_the_fragment() -> None:
    session = _session(wdk_step_tree=WDKStepTree(step_id=_GO_WDK))
    graph = session.graph
    assert graph is not None

    data = graph_snapshot_chunk(session, graph).data

    assert data["geneCount"] == 1282
    assert data["detachedStepCount"] == 1


def test_the_metadata_cites_the_strategy_root_too() -> None:
    session = _session(wdk_step_tree=WDKStepTree(step_id=_TEXT_WDK))
    graph = session.graph
    assert graph is not None

    data = strategy_meta_chunk(session, graph).data

    assert data["estimatedSize"] == 61


async def test_the_strategy_summary_cites_the_same_root() -> None:
    session = _session(wdk_step_tree=WDKStepTree(step_id=_GO_WDK))
    ctx = agent_run_context(strategy_session=session)

    chunk = summary_of(await strategy_graph.get_strategy(ctx))

    assert chunk.data["summary"] == "2 steps, 1,282 transcripts"


def test_a_split_graph_no_push_identifies_names_the_split_anyway() -> None:
    """No root is citable, and the reader still learns the graph is split."""
    session = _session(wdk_step_tree=None)
    graph = session.graph
    assert graph is not None

    data = graph_snapshot_chunk(session, graph).data

    assert data["geneCount"] is None
    assert data["detachedStepCount"] == 1


def test_a_strategy_root_with_no_citable_count_reports_none() -> None:
    session = _session(wdk_step_tree=WDKStepTree(step_id=_GO_WDK))
    sync_state = session.sync_state
    assert sync_state is not None
    sync_state.wdk_push_errors[_GO] = "422 organism: Invalid value"
    graph = session.graph
    assert graph is not None

    data = graph_snapshot_chunk(session, graph).data

    assert data["geneCount"] is None
    assert data["detachedStepCount"] == 1


def test_a_one_root_graph_is_unchanged() -> None:
    session = _one_root_session()
    graph = session.graph
    assert graph is not None

    data = graph_snapshot_chunk(session, graph).data

    assert data["geneCount"] == 1282
    assert data["detachedStepCount"] == 0
