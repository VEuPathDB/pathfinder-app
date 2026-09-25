"""A step whose last push VEuPathDB refused is cited with no count anywhere."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.tools.standalone import strategy_graph
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.graph_outcome import outcome_for_graph
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_STEP = "step_a1b2c3d4"
_REFUSAL = "422 organism: Invalid value 'Pfal3D7 Gametocyte time course'."


def _sync_state() -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids={_STEP: 440_432_473},
        step_counts={_STEP: 1282},
        wdk_push_errors={_STEP: _REFUSAL},
        wdk_strategy_id=330_642_473,
    )


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id=_STEP, search_name="GenesByMicroarrayBirkholtz")
    )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = _sync_state()
    return session


async def test_the_strategy_summary_says_the_count_is_not_available() -> None:
    ctx = agent_run_context(strategy_session=_session())

    chunk = summary_of(await strategy_graph.get_strategy(ctx))

    assert chunk.data["summary"] == "1 step, count not available"
    assert chunk.data["status"] == "warn"


def test_the_build_outcome_reports_no_root_count() -> None:
    session = _session()

    outcome = outcome_for_graph(
        graph=session.graph,
        sync_state=_sync_state(),
        counts={_STEP: 1282},
        failed_step_ids=[_STEP],
        wdk_url=None,
    )

    assert outcome.root_count is None
    assert [node.count for node in outcome.node_results] == [None]
    assert [node.status for node in outcome.node_results] == ["failed"]
