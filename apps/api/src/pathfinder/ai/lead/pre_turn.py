"""PathFinder's pre-turn work: measure the recorded build against WDK, play
what was written outside this thread onto every spec the turn holds, give a
strategy that has no spec one derived from what it already is, and brief the
turn on what moved since the thread last answered.

The user can edit the strategy between turns, in the graph editor or on the
site. WDK owns it, so only WDK can say what it holds now.
"""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.answered_strategy import (
    live_tree,
    the_changes_written_outside,
    the_strategy_now_answers_to,
)
from pathfinder.ai.lead.turn_briefing import compose_turn_briefing
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_hydration import (
    hidden_params_dropped,
    spec_from_ast,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_the_strategy_holds
from pathfinder.domain.strategy.staleness import detect_build_staleness
from pathfinder.services.conversations.thread_activity import read_thread_activity
from pathfinder.services.eda.binding import open_analysis_in
from pathfinder.services.strategies.live_counts import read_wdk_step_counts
from pathfinder.services.strategies.sheet_params import sheet_params_for_searches

__all__ = [
    "attach_open_eda_analysis",
    "attach_turn_briefing",
    "pathfinder_pre_turn",
    "refresh_live_strategy_state",
]


async def pathfinder_pre_turn(
    state: PipelineState,
    context: Context,
) -> PipelineState:
    """The state the turn runs on: refreshed against WDK, then briefed."""
    answered = state.domain.answered_graph
    refreshed = await refresh_live_strategy_state(state, context)
    briefed = await attach_turn_briefing(refreshed, context, answered=answered)
    return await attach_open_eda_analysis(briefed, context)


async def attach_turn_briefing(
    state: PipelineState,
    context: Context,
    *,
    answered: StrategyAst | None,
) -> PipelineState:
    """Render what moved since the thread last answered onto the state.

    ``answered`` is the tree the thread's spec answered to when the turn
    opened, which the refresh has already brought up to the live one.
    """
    async with context.db_session_factory() as session:
        activity = await read_thread_activity(
            session,
            conversation_id=state.conversation_id,
        )
    state.domain.turn_briefing = compose_turn_briefing(
        activity,
        requirements=state.domain.requirements,
        answered=answered,
        live=live_tree(context.strategy_session.get_graph(None)),
    ).render()
    return state


async def attach_open_eda_analysis(
    state: PipelineState,
    context: Context,
) -> PipelineState:
    """Read the analysis the thread holds open onto the state.

    The binding and its preview outlive the message that made them, so the
    turn reads them rather than what this message did.
    """
    async with context.db_session_factory() as session:
        bound = await open_analysis_in(session, conversation_id=state.conversation_id)
    state.domain.open_eda_analysis = (
        None
        if bound is None
        else OpenEdaAnalysis(
            dataset_id=bound.dataset_id,
            analysis_id=bound.analysis_id,
            subset_previewed=bound.subset_previewed,
        )
    )
    return state


async def refresh_live_strategy_state(
    state: PipelineState,
    context: Context,
) -> PipelineState:
    """Return the state the turn runs on, with staleness measured live, what
    was written outside played onto every spec, and the spec reconstructed
    when the strategy has one and the checkpoint does not."""
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
    await _answer_what_was_written_outside(working_state, context)
    await _hydrate_spec_from_the_strategy(working_state, context)
    _record_the_spec_the_turn_started_from(working_state)
    return working_state


async def _answer_what_was_written_outside(
    state: PipelineState, context: Context
) -> None:
    """Play every change made outside this thread onto every spec it holds.

    A resumed call and a finished background task both re-enter the turn on
    this path, so it runs whatever opened the turn: a spec that skipped it
    would plan against a strategy the researcher no longer has.
    """
    graph = context.strategy_session.get_graph(None)
    if graph is None:
        return
    if state.domain.answered_spec is None and graph.steps:
        _initialise_the_answered_facts(state, graph)
    await the_changes_written_outside(state, site_id=context.site_id, graph=graph)


def _initialise_the_answered_facts(state: PipelineState, graph: StrategyGraph) -> None:
    """Record what an existing thread's strategy already answers to.

    The answer is the plan, or the spec the last dispatch found when the plan
    runs ahead of the strategy, in both cases without the criteria its
    structure names and the strategy holds no step for. Nothing is replayed
    that turn: what moved before the first record is not attributable to
    anyone.
    """
    domain = state.domain
    plan = domain.operational_spec
    found = domain.spec_before_dispatch
    source = found if found is not None and _runs_ahead(plan, graph) else plan
    the_strategy_now_answers_to(state, _the_built_part_of(source, graph), graph)


def _runs_ahead(spec: OperationalSpec | None, graph: StrategyGraph) -> bool:
    """Whether this plan states more than the strategy has reached.

    A plan that is not ready to build holds an answer the thread is still
    waiting for, and one whose structure names a criterion with no live step
    holds a criterion the strategy has not built. Either way the spec the last
    dispatch found is what the strategy answers to.
    """
    if spec is None or not spec.ready_to_build:
        return True
    return bool(structure_criteria(spec.structure) - set(graph.steps))


def _the_built_part_of(
    spec: OperationalSpec | None, graph: StrategyGraph
) -> OperationalSpec | None:
    if spec is None:
        return None
    return spec_the_strategy_holds(spec, graph.steps)


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
    stated = hidden_params_dropped(hydrated, sheet_params=sheets)
    state.domain.operational_spec = stated
    the_strategy_now_answers_to(state, stated, graph)
