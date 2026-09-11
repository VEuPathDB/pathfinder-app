"""The Lead's edit dispatch: a delta over the strategy that already exists.

FRAME runs over the spec the turn started from, the two are compared, and the
difference is pushed as graph operations. A step the edit does not name keeps
its WDK id and every value the researcher set on it.
"""

from __future__ import annotations

from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    refuse_and_restore,
)
from pathfinder.ai.lead.edit_messages import (
    changed_revision_message,
    edit_bound_nothing_message,
    edit_work_order,
    no_strategy_to_edit_message,
    unsupported_edit_message,
)
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import SpecDiff, diff_specs
from pathfinder.domain.strategy.spec_to_operations import (
    UnsupportedEditError,
    operations_for,
)
from pathfinder.services.strategies.commit import (
    CommitResult,
    apply_operations_and_commit,
)
from pathfinder.services.strategies.graph_outcome import outcome_for_graph
from pathfinder.services.strategies.live_counts import read_wdk_step_counts
from pathfinder.services.strategies.sync_state import ensure_sync_state

__all__ = ["edit_strategy", "run_edit"]


async def run_edit(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> EditDelta | SubAgentApprovalWait:
    """Run the edit and push it, on a fresh dispatch or a resumed one."""
    before = deps.state.domain.spec_before_turn
    graph = deps.runtime.strategy_session.get_graph(None)
    if before is None or not before.criteria or graph is None or not graph.steps:
        # Nothing has been written yet, so the refusal restores nothing: a spec
        # this turn framed for a fresh thread must survive a misrouted call.
        raise ModelRetry(no_strategy_to_edit_message())
    base_revision = strategy_revision(graph.to_strategy_ast())
    frame = await run_frame(
        deps=deps,
        parent_tool_call_id=parent_tool_call_id,
        work_order=edit_work_order(reason, deps.state.user_prompt, before),
        expected_criteria=len(before.criteria),
        resume=resume,
    )
    if isinstance(frame, SubAgentApprovalWait):
        return frame
    after = deps.state.domain.operational_spec
    if after is None or not after.criteria:
        refuse_and_restore(deps, edit_bound_nothing_message())
    diff = diff_specs(before, after)
    if frame.disposition != "spec_ready":
        return EditDelta(
            diff=diff,
            disposition="needs_user",
            summary=frame.summary,
            open_questions=list(frame.open_questions),
        )
    return await _push_the_edit(
        deps=deps,
        before=before,
        after=after,
        diff=diff,
        graph=graph,
        base_revision=base_revision,
    )


async def _push_the_edit(
    *,
    deps: LeadDeps,
    before: OperationalSpec,
    after: OperationalSpec,
    diff: SpecDiff,
    graph: StrategyGraph,
    base_revision: str,
) -> EditDelta:
    try:
        ops = operations_for(diff, before=before, after=after, graph=graph)
    except (UnsupportedEditError, ApplyError) as exc:
        refuse_and_restore(deps, unsupported_edit_message(str(exc)))
    preserved = [c.criterion_id for c in diff.changes if c.disposition == "kept"]
    if not ops:
        return EditDelta(
            diff=diff,
            description="The strategy already states everything the edit asks for.",
            preserved_step_ids=preserved,
        )
    current = strategy_revision(graph.to_strategy_ast())
    if current != base_revision:
        refuse_and_restore(deps, changed_revision_message(base_revision, current))
    agent_deps = agent_deps_for(deps)
    try:
        commit = await apply_operations_and_commit(
            deps=agent_deps.to_strategy_context(), ops=ops
        )
    except ApplyError as exc:
        # The batch rolls back, so the strategy is exactly as it was.
        refuse_and_restore(deps, unsupported_edit_message(str(exc)))
    outcome = await _outcome_after_edit(agent_deps, commit)
    deps.state.record_build(outcome)
    _emit_graph_snapshot(agent_deps)
    return EditDelta(
        diff=diff,
        description=commit.description,
        operations_applied=len(ops),
        preserved_step_ids=preserved,
        dropped_step_ids=list(commit.dropped_step_ids),
        failed_step_ids=list(commit.failed_step_ids),
    )


async def _outcome_after_edit(
    agent_deps: AgentDeps, commit: CommitResult
) -> BuildOutcome:
    """The build the edit leaves behind, with counts read from WDK.

    A pushed step's stored count describes the step before the edit, so the
    numbers the Lead reports are read again rather than carried over.
    """
    session = agent_deps.strategy_session
    sync_state = ensure_sync_state(session)
    counts = await read_wdk_step_counts(sync_state, agent_deps.site_id)
    return outcome_for_graph(
        graph=session.get_graph(None),
        sync_state=sync_state,
        counts=counts,
        failed_step_ids=commit.failed_step_ids,
        wdk_url=commit.sync_result.wdk_url if commit.sync_result else None,
    )


def _emit_graph_snapshot(agent_deps: AgentDeps) -> None:
    session = agent_deps.strategy_session
    graph = session.get_graph(None)
    if graph is None:
        return
    emit_chunk(get_stream_writer(), graph_snapshot_chunk(session, graph))


async def edit_strategy(ctx: RunContext[LeadDeps], reason: str) -> EditDelta:
    """Change the strategy that already exists, in place.

    Use this for every request that starts from the strategy on the user's
    screen: substitute a value, add a criterion, drop one, change a combine.
    It re-frames only the criteria the request names, pushes the difference as
    step edits, and leaves every other step's WDK id and values untouched.
    ``build_strategy`` replaces a strategy wholesale and is not the tool for an
    edit.

    ``reason`` is what the request changes, in one sentence.

    The returned ``EditDelta`` carries the computed ``diff``: every claim in
    your reply that something was kept, changed, added or dropped is read from
    it and from nothing else.
    """
    tool_call_id = dispatch_call_id(ctx)
    result = await run_edit(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        reason=reason,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
    return result
