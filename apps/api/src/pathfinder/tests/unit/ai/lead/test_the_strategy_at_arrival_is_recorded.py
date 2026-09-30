"""The turn records the strategy the message found once, before any tool runs,
and every count before an edit is read from that record."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.graph.turn_records import CountsAtArrival
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.tests.unit.ai.lead.conftest import lead_runtime, pipeline_state

# The C. neoformans volcano export intersected with a text search.
_COUNTS = {"step_volcano": 8, "step_text": 312, "step_join": 3}


def _session() -> StrategySession:
    root = StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(id="step_volcano", search_name="GenesByEda"),
        secondary_input=StrategyStepNode(id="step_text", search_name="GenesByText"),
    )
    graph = StrategyGraph(graph_id="g1", name="volcano", site_id="fungidb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id="fungidb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts=dict(_COUNTS))
    return session


def _state() -> PipelineState:
    """A thread whose spec already states both searches, so nothing is hydrated."""
    spec = OperationalSpec(
        goal="genes higher at 37 degrees",
        criteria=[
            Criterion(id="step_volcano", text="higher at 37", search_name="GenesByEda"),
            Criterion(id="step_text", text="kinase", search_name="GenesByText"),
        ],
    )
    return pipeline_state(
        "fungidb",
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec),
    )


async def test_the_turn_records_the_root_and_every_count_the_message_found() -> None:
    session = _session()
    state = _state()

    refreshed = await refresh_live_strategy_state(
        state, lead_runtime(strategy_session=session)
    )

    assert refreshed.turn_markers.at_arrival == CountsAtArrival(
        root_id="step_join", counts=_COUNTS
    )


async def test_a_resumed_turn_keeps_the_record_its_message_made() -> None:
    session = _session()
    state = _state()
    first = await refresh_live_strategy_state(
        state, lead_runtime(strategy_session=session)
    )
    ensure_sync_state(session).step_counts = {**_COUNTS, "step_join": 0}

    resumed = await refresh_live_strategy_state(
        first, lead_runtime(strategy_session=session)
    )

    assert resumed.turn_markers.at_arrival == first.turn_markers.at_arrival
