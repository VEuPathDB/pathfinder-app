"""The Lead's edit dispatch: a delta over the strategy that already exists.

FRAME runs over the spec the dispatch found on the strategy, the two are
compared, and the difference is pushed as graph operations. A step the edit
does not name keeps its WDK id and every value the researcher set on it.
"""

from __future__ import annotations

import pydantic
from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.errors import ParamMessages, ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    record_the_spec_the_dispatch_found,
    refuse_and_restore,
)
from pathfinder.ai.lead.dispatch_messages import option_binds_no_step_message
from pathfinder.ai.lead.edit_messages import (
    changed_revision_message,
    edit_bound_nothing_message,
    edit_work_order,
    no_strategy_to_edit_message,
    unsupported_edit_message,
    wdk_refused_the_written_step_message,
)
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.strategy_refusals import wdk_refused_the_edit
from pathfinder.ai.tools.standalone.stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    fold_option_criteria,
)
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
    record_the_spec_the_dispatch_found(deps, resume=resume)
    before = deps.state.domain.spec_before_dispatch
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
    # Both sides state an option as a value on the step that runs its search,
    # so the difference between them is a difference between steps. The stored
    # spec is what an earlier turn left, so only this turn's side is refused.
    before = fold_option_criteria(before).spec
    folded_after = fold_option_criteria(after)
    if folded_after.unplaced:
        refuse_and_restore(
            deps, option_binds_no_step_message(folded_after.spec, folded_after.unplaced)
        )
    after = folded_after.spec
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
    except ValidationError as exc:
        refuse_and_restore(deps, _refused_values_message(exc, diff=diff, after=after))
    outcome = await _outcome_after_edit(agent_deps, commit)
    # The spec the thread carries states the option on the step that runs it,
    # exactly as the spec a build leaves behind does.
    deps.state.domain.operational_spec = after
    deps.state.record_build(outcome)
    _emit_graph_snapshot(agent_deps)
    # A push VEuPathDB did not take is the answer. The applied-operation line
    # would read as a success the strategy does not hold.
    refusal = wdk_refused_the_edit(commit)
    return EditDelta(
        diff=diff,
        description=commit.description if refusal is None else refusal.message,
        operations_applied=len(ops),
        preserved_step_ids=preserved,
        dropped_step_ids=list(commit.dropped_step_ids),
        failed_step_ids=list(commit.failed_step_ids),
    )


_REFUSED_PARAMS = pydantic.TypeAdapter(list[ParamMessages])


def _params_wdk_named(exc: ValidationError) -> frozenset[str]:
    """The parameter names the refusal rows carry, empty when it carries none."""
    try:
        rows = _REFUSED_PARAMS.validate_python(exc.errors or [])
    except pydantic.ValidationError:
        return frozenset()
    return frozenset(row.param for row in rows)


def _steps_the_edit_writes(diff: SpecDiff, after: OperationalSpec) -> list[Criterion]:
    """The criteria whose values this edit sends to VEuPathDB."""
    written = {
        change.criterion_id
        for change in diff.changes
        if change.disposition in {"added", "changed"}
    }
    return [criterion for criterion in after.criteria if criterion.id in written]


def _refused_values_message(
    exc: ValidationError, *, diff: SpecDiff, after: OperationalSpec
) -> str:
    """The refusal for values VEuPathDB turned down while the edit was pushed.

    The refused step is the one this edit writes that states a parameter the
    answer names; every written step is named when the answer names none.
    """
    params = _params_wdk_named(exc)
    written = _steps_the_edit_writes(diff, after)
    named = [c for c in written if not params.isdisjoint(c.resolved_params)]
    return wdk_refused_the_written_step_message(
        exc.detail or str(exc),
        steps=[f"[{c.id}] {c.search_name}" for c in (named or written)],
        params=sorted(params),
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
