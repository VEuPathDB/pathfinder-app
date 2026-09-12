"""The graph snapshot and the strategy metadata carry no number when no count
was measured for the step."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.tools.standalone._stream_parts import (
    graph_snapshot_chunk,
    strategy_meta_chunk,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState

_STEP = "step_a1b2c3d4"
_SEARCH = "GenesByMicroarrayBirkholtz"
_REFUSAL = "422 profileset_generic: Invalid value"


def _snapshot(count: int | None) -> dict[str, object]:
    return {
        "strategyId": "g1",
        "geneCount": count,
        "nodes": [{"id": _STEP, "searchName": _SEARCH, "estimatedSize": count}],
        "edges": [],
    }


def _meta(count: int | None) -> dict[str, object]:
    return {
        "strategyId": "g1",
        "name": "Kinases",
        "isSaved": False,
        "estimatedSize": count,
        "recordClassName": "transcript",
    }


def _session(
    *, count: int | None, refusal: str | None
) -> tuple[StrategySession, StrategyGraph]:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id=_STEP, search_name=_SEARCH))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={_STEP: 440_432_473},
        step_counts={_STEP: count},
        wdk_push_errors={} if refusal is None else {_STEP: refusal},
        wdk_strategy_id=330_642_473,
    )
    return session, graph


def test_the_snapshot_sends_no_count_for_a_step_nobody_measured() -> None:
    session, graph = _session(count=None, refusal=_REFUSAL)

    data = graph_snapshot_chunk(session, graph).data

    assert data == _snapshot(None)


def test_the_metadata_sends_no_count_for_a_step_nobody_measured() -> None:
    session, graph = _session(count=None, refusal=_REFUSAL)

    data = strategy_meta_chunk(session, graph).data

    assert data == _meta(None)


def test_the_snapshot_sends_no_count_for_a_refused_step_that_carries_one() -> None:
    session, graph = _session(count=1282, refusal=_REFUSAL)

    data = graph_snapshot_chunk(session, graph).data

    assert data == _snapshot(None)


def test_a_measured_zero_stays_zero() -> None:
    session, graph = _session(count=0, refusal=None)

    snapshot = graph_snapshot_chunk(session, graph).data
    meta = strategy_meta_chunk(session, graph).data

    assert snapshot == _snapshot(0)
    assert meta == _meta(0)


def test_a_measured_count_is_sent_as_it_stands() -> None:
    session, graph = _session(count=1282, refusal=None)

    snapshot = graph_snapshot_chunk(session, graph).data
    meta = strategy_meta_chunk(session, graph).data

    assert snapshot == _snapshot(1282)
    assert meta == _meta(1282)
