"""The thread holds one graph, so the strategy read names none and a repeat is one read."""

from __future__ import annotations

import inspect

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.tools.standalone.strategy_graph import (
    StrategySummaryResponse,
    get_strategy,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_STEP = "step_353195e7"
_STEP_WDK = 441_030_503
_STRATEGY_WDK = 330_642_473


def _built() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Antigens", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id=_STEP, search_name="GenesByText"))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={_STEP: _STEP_WDK},
        step_counts={_STEP: 288},
        wdk_strategy_id=_STRATEGY_WDK,
    )
    return session


def test_the_strategy_read_takes_no_graph_id() -> None:
    """Three names for one graph would be three reads of it."""
    assert list(inspect.signature(get_strategy).parameters) == ["ctx", "summary_only"]


async def test_the_read_answers_the_threads_graph() -> None:
    ctx = agent_run_context(strategy_session=_built())

    read = returned(
        await get_strategy(ctx, summary_only=False), StrategySummaryResponse
    )

    assert (read.graph_id, read.step_count, read.wdk_strategy_id) == (
        "g1",
        1,
        _STRATEGY_WDK,
    )


async def test_a_thread_with_no_strategy_says_so() -> None:
    ctx = agent_run_context(strategy_session=StrategySession(site_id="plasmodb"))

    result = await get_strategy(ctx)

    assert returned(result, ToolErrorPayload).message == (
        "This conversation holds no strategy yet."
    )
    assert summary_of(result).model_dump(by_alias=True)["data"]["summary"] == (
        "No strategy yet"
    )
