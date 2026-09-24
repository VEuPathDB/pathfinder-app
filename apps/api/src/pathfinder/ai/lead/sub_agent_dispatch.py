"""The Lead's build and recovery dispatch tools.

The declarative build of the operational spec, and the recovery pass a failed
build re-enters.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.errors import VEuPathDBError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.answered_strategy import (
    live_tree,
    the_strategy_now_answers_to,
    the_thread_wrote_the_strategy,
)
from pathfinder.ai.lead.build_messages import (
    build_not_ready_message,
    build_would_replace_the_strategy,
    structure_does_not_convert_message,
)
from pathfinder.ai.lead.deltas import ExecuteDelta, RecoveryDelta
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
)
from pathfinder.ai.lead.dispatch_messages import option_binds_no_step_message
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.tools.standalone.graph_helpers import derive_strategy_name
from pathfinder.ai.tools.standalone.strategy_refusals import (
    build_departs_from_the_plan_message,
)
from pathfinder.ai.tools.standalone.stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_fold import (
    fold_option_criteria,
)
from pathfinder.domain.strategy.spec_reconciliation import (
    spec_without_pending_analyses,
)
from pathfinder.domain.strategy.spec_tree import (
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.step_words import added_searches, step_words
from pathfinder.services.strategies.auto_import import (
    import_gene_set_for_conversation,
)
from pathfinder.services.strategies.spec_build import (
    build_strategy_from_spec,
    node_results,
)
from pathfinder.services.strategies.sync import sync_strategy_for_site
from pathfinder.services.strategies.sync_state import ensure_sync_state


async def build_strategy(ctx: RunContext[LeadDeps]) -> ExecuteDelta:
    """Materialize the OperationalSpec into a real WDK strategy declaratively
    (no LLM). Requires ``frame_problem`` first. Inspect ``ledger.build`` after
    to decide ``recover_failed_steps`` or ``verify_strategy``.

    Available while the thread holds no strategy: it would replace one that
    exists. Call ``edit_strategy`` to change a strategy, or ask the user how
    to start over."""
    deps = ctx.deps
    steps = deps.step_count
    if steps:
        raise ModelRetry(build_would_replace_the_strategy(steps))
    spec = deps.state.domain.operational_spec
    if spec is None or not spec.ready_to_build:
        raise ModelRetry(build_not_ready_message(spec))
    # A criterion the structure leaves out states an option on the search a
    # step runs, so its values join that step before the tree is minted.
    folded = fold_option_criteria(spec)
    if folded.unplaced:
        raise ModelRetry(option_binds_no_step_message(folded.spec, folded.unplaced))
    spec = folded.spec
    try:
        # A criterion waiting for its analysis has no search to mint, so the
        # EDA tools add its step once the rest is built.
        built = build_step_tree(spec_without_pending_analyses(spec))
    except ValueError as exc:
        raise ModelRetry(structure_does_not_convert_message(str(exc))) from exc
    agent_deps = agent_deps_for(deps)
    context = replace(
        agent_deps.to_strategy_context(),
        step_words=step_words(spec, built.step_id_by_criterion),
    )
    try:
        outcome: BuildOutcome = await build_strategy_from_spec(
            deps=context, root=built.root
        )
    except ApplyError as exc:
        raise ModelRetry(build_departs_from_the_plan_message(str(exc))) from exc
    # A criterion and the step it built become one address, so the next turn's
    # edit changes that step instead of rebuilding the strategy around it.
    # The build re-keys the criteria without changing what they state, so every
    # record the turn holds moves to the same addresses and the diff reads kept.
    deps.state.domain.restate_every_record(
        built.step_id_by_criterion,
        lambda held: renumber_criteria(held, built.step_id_by_criterion),
    )
    renumbered = renumber_criteria(spec, built.step_id_by_criterion)
    deps.state.domain.operational_spec = renumbered
    deps.state.record_build(outcome)
    added = added_searches(renumbered, built.step_id_by_criterion.values())
    deps.state.turn_markers.record_added_searches(added)
    graph = agent_deps.strategy_session.get_graph(None)
    # The whole local tree is persisted even when a push fails part way, so
    # the renumbered spec is what the strategy answers to either way.
    the_strategy_now_answers_to(deps.state, renumbered, graph)
    if graph is not None:
        emit_chunk(
            get_stream_writer(),
            graph_snapshot_chunk(agent_deps.strategy_session, graph),
        )
    if (
        outcome.wdk_strategy_id is not None
        and graph is not None
        and agent_deps.user_id is not None
        and agent_deps.conversation_id is not None
    ):
        await import_gene_set_for_conversation(
            conversation_id=agent_deps.conversation_id,
            site_id=agent_deps.site_id,
            user_id=agent_deps.user_id,
            name=_gene_set_name(renumbered, graph),
        )
    return ExecuteDelta(outcome=outcome, added_searches=added)


_SET_NAME_LENGTH = 60


def _gene_set_name(spec: OperationalSpec, graph: StrategyGraph) -> str:
    """The name the thread's gene set takes until the thread has a title."""
    stated = (spec.interpreted_goal or spec.goal).strip().splitlines()
    if stated:
        return stated[0].strip()[:_SET_NAME_LENGTH].rstrip()
    root = graph.steps.get(graph.primary_root_id() or "")
    return graph.name if root is None else derive_strategy_name(graph.record_type, root)


async def run_recovery(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> RecoveryDelta | SubAgentApprovalWait:
    """Run recovery and re-sync the build, on a fresh dispatch or a resumed one."""
    outcome = deps.state.domain.last_build_outcome
    if outcome is None:
        msg = "No build outcome to recover from."
        raise RuntimeError(msg)
    work_order_parts = [
        f"Recovery work order: {reason}",
        f"Failed steps: {len(outcome.failed_steps)}",
        f"Skipped: {len(outcome.skipped_step_ids)}",
        f"Zero-result: {len(outcome.zero_step_ids)}",
        "Edit the affected steps via update_leaf_params / replace_subtree.",
        "Return a RecoveryDelta with actions_taken and final_outcome.",
    ]
    work_order = "\n".join(work_order_parts)
    session = deps.runtime.strategy_session
    before = _written_strategy(session)
    tree_before = live_tree(session.get_graph(None))
    agent_deps = agent_deps_for(deps)
    streamed = await stream_sub_agent(
        run=PhaseRun("execution", work_order),
        agent_deps=agent_deps,
        parent_tool_call_id=parent_tool_call_id,
        expected_output_type=RecoveryDelta,
        deps=deps,
        resume=resume,
    )
    if isinstance(streamed, SubAgentApprovalWait):
        return streamed
    apply_agent_state(deps, agent_deps)
    delta = streamed if streamed is not None else RecoveryDelta()
    resynced = await _resync_outcome(agent_deps, outcome)
    # Recovery writes the steps and never the spec, so the spec takes what it
    # wrote rather than reading it as the researcher's own edit next turn.
    await the_thread_wrote_the_strategy(
        deps.state,
        site_id=deps.runtime.site_id,
        graph=session.get_graph(None),
        before=tree_before,
    )
    if _written_strategy(session) == before:
        deps.state.record_resync(resynced)
    else:
        deps.state.record_build(resynced)
    return delta


async def recover_failed_steps(
    ctx: RunContext[LeadDeps],
    reason: str,
) -> RecoveryDelta:
    """Run the LLM execution-recovery sub-agent on a failed build.

    Only valid when ``ledger.build.needs_recovery`` is True and the
    failure shape is amenable to targeted edits (param replan, partial
    build). When a criterion needs a different search entirely, re-bind it
    with ``edit_strategy``, or tell the researcher which criterion needs a
    different search and end the turn.
    """
    tool_call_id = dispatch_call_id(ctx)
    result = await run_recovery(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        reason=reason,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
    return result


@dataclass(frozen=True)
class _WrittenStrategy:
    """What the thread plans and what VEuPathDB holds of it.

    A pass that leaves both alone wrote nothing, whatever it reported.
    """

    revision: str
    wdk_step_ids: tuple[tuple[str, int], ...]


def _written_strategy(session: StrategySession) -> _WrittenStrategy:
    graph = session.get_graph(None)
    return _WrittenStrategy(
        revision="" if graph is None else strategy_revision(graph.to_strategy_ast()),
        wdk_step_ids=tuple(sorted(ensure_sync_state(session).wdk_step_ids.items())),
    )


async def _resync_outcome(agent_deps: AgentDeps, prior: BuildOutcome) -> BuildOutcome:
    """Re-derive the BuildOutcome after recovery edits by re-syncing the
    strategy. The recovery agent no longer emits the outcome itself."""
    graph = agent_deps.strategy_session.get_graph(None)
    if graph is None:
        return prior
    sync_state = ensure_sync_state(agent_deps.strategy_session)
    try:
        sync_result = await sync_strategy_for_site(
            graph=graph,
            sync_state=sync_state,
            site_id=agent_deps.site_id,
            user_prompt=agent_deps.user_prompt,
        )
    except VEuPathDBError:
        return prior
    fresh = BuildOutcome(
        pushed_step_ids=list(prior.pushed_step_ids),
        wdk_strategy_id=sync_result.wdk_strategy_id,
        wdk_url=sync_result.wdk_url,
        counts={str(k): v for k, v in sync_result.counts.items()},
        root_count=sync_result.root_count,
        zero_step_ids=list(sync_result.zero_step_ids),
    )
    fresh.node_results = node_results(list(graph.steps.values()), sync_state, fresh)
    return fresh
