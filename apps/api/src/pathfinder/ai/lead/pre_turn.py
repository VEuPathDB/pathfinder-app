"""PathFinder's pre-turn work: measure the recorded build against WDK, give a
strategy that has no spec one derived from what it already is, and brief the
turn on what moved since the thread last answered.

The user can edit the strategy between turns, in the graph editor or on the
site. WDK owns it, so only WDK can say what it holds now.
"""

from __future__ import annotations

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.turn_briefing import compose_turn_briefing
from pathfinder.domain.strategy.spec_hydration import (
    hidden_params_dropped,
    spec_from_ast,
)
from pathfinder.domain.strategy.staleness import detect_build_staleness
from pathfinder.services.conversations.thread_activity import read_thread_activity
from pathfinder.services.strategies.live_counts import read_wdk_step_counts
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches

__all__ = [
    "attach_turn_briefing",
    "pathfinder_pre_turn",
    "refresh_live_strategy_state",
]


async def pathfinder_pre_turn(
    state: PipelineState,
    context: Context,
) -> PipelineState:
    """The state the turn runs on: refreshed against WDK, then briefed."""
    refreshed = await refresh_live_strategy_state(state, context)
    return await attach_turn_briefing(refreshed, context)


async def attach_turn_briefing(
    state: PipelineState,
    context: Context,
) -> PipelineState:
    """Render what moved since the thread last answered onto the state."""
    async with context.db_session_factory() as session:
        activity = await read_thread_activity(
            session,
            conversation_id=state.conversation_id,
        )
    state.domain.turn_briefing = compose_turn_briefing(
        activity,
        requirements=state.domain.requirements,
    ).render()
    return state


async def refresh_live_strategy_state(
    state: PipelineState,
    context: Context,
) -> PipelineState:
    """Return the state the turn runs on, with staleness measured live and the
    spec reconstructed when the strategy has one and the checkpoint does not."""
    working_state = state.model_copy(deep=True)
    sync_state = context.strategy_session.sync_state
    live_counts = (
        await read_wdk_step_counts(sync_state, context.site_id)
        if sync_state is not None
        else {}
    )
    working_state.domain.stale_build = detect_build_staleness(
        working_state.domain.last_build_outcome,
        live_counts,
    )
    await _hydrate_spec_from_the_strategy(working_state, context)
    _record_the_spec_the_turn_started_from(working_state)
    return working_state


def _record_the_spec_the_turn_started_from(state: PipelineState) -> None:
    """Keep the entry spec an edit's dispositions are checked against.

    A turn that resumes a parked call continues the turn that already
    recorded one, so it keeps that record rather than the spec the suspended
    pass had reached.
    """
    if state.resumes_parked_call:
        return
    entry_spec = state.domain.operational_spec
    state.domain.spec_before_turn = (
        None if entry_spec is None else entry_spec.model_copy(deep=True)
    )


async def _hydrate_spec_from_the_strategy(
    state: PipelineState, context: Context
) -> None:
    """Describe the live strategy as a spec when no framed spec describes it.

    The graph editor, a saved-strategy import and a checkpoint flush all leave
    a real strategy behind with nothing that says what it asks. The stored step
    also carries WDK's own parameters, and the criterion states only the ones
    the search's sheet shows.
    """
    spec = state.domain.operational_spec
    if spec is not None and spec.criteria:
        return
    graph = context.strategy_session.get_graph(None)
    if graph is None or not graph.steps:
        return
    ast = graph.to_strategy_ast(sync_state=context.strategy_session.sync_state)
    if ast is None:
        return
    hydrated = spec_from_ast(ast, goal=state.user_prompt)
    sheets = await sheet_params_for_searches(
        site_id=context.site_id,
        record_type=ast.record_type,
        search_names=[c.search_name for c in hydrated.criteria if c.search_name],
    )
    state.domain.operational_spec = hidden_params_dropped(hydrated, sheet_params=sheets)
