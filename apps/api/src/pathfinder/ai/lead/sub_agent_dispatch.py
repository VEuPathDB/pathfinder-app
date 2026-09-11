"""The Lead's build and recovery dispatch tools.

The declarative build of the operational spec, and the recovery pass a failed
build re-enters.
"""

from __future__ import annotations

from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.errors import VEuPathDBError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import ExecuteDelta, RecoveryDelta
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
)
from pathfinder.ai.lead.dispatch_messages import (
    build_not_ready_message,
    build_would_replace_the_strategy,
)
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.tools.standalone._stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    build_step_tree,
    renumber_criteria,
)
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
    graph = deps.runtime.strategy_session.get_graph(None)
    if graph is not None and graph.steps:
        raise ModelRetry(build_would_replace_the_strategy(len(graph.steps)))
    spec = deps.state.domain.operational_spec
    if spec is None or not spec.ready_to_build:
        raise ModelRetry(build_not_ready_message(spec))
    # Readiness says every criterion is bound and a structure exists. Only the
    # conversion knows whether that structure is a tree WDK can hold.
    try:
        built = build_step_tree(spec)
    except ValueError as exc:
        msg = (
            f"The spec is bound but its structure does not convert: {exc}. "
            "Call set_structure with a tree whose every combine names an "
            "operator and joins two inputs."
        )
        raise ModelRetry(msg) from exc
    agent_deps = agent_deps_for(deps)
    outcome: BuildOutcome = await build_strategy_from_spec(
        deps=agent_deps.to_strategy_context(),
        root=built.root,
        name=spec.title or None,
    )
    # A criterion and the step it built become one address, so the next turn's
    # edit changes that step instead of rebuilding the strategy around it.
    deps.state.domain.operational_spec = renumber_criteria(
        spec, built.step_id_by_criterion
    )
    deps.state.record_build(outcome)
    graph = agent_deps.strategy_session.get_graph(None)
    if graph is not None:
        emit_chunk(
            get_stream_writer(),
            graph_snapshot_chunk(agent_deps.strategy_session, graph),
        )
    if (
        outcome.wdk_strategy_id is not None
        and agent_deps.user_id is not None
        and agent_deps.conversation_id is not None
    ):
        await import_gene_set_for_conversation(
            conversation_id=agent_deps.conversation_id,
            site_id=agent_deps.site_id,
            user_id=agent_deps.user_id,
        )
    return ExecuteDelta(outcome=outcome)


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
    deps.state.record_build(await _resync_outcome(agent_deps, outcome))
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
            strategy_name=graph.name,
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
