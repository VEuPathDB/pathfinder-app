"""The Lead's edit dispatch: a delta over the strategy that already exists.

FRAME runs over the spec the dispatch found on the strategy, the two are
compared, and the difference is pushed as graph operations. A step the edit
does not name keeps its WDK id and every value the researcher set on it.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

import pydantic
from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.errors import ParamMessages, ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.answered_strategy import the_strategy_now_answers_to
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    record_the_spec_the_dispatch_found,
    refuse_and_restore,
    the_edit_the_strategy_owes,
)
from pathfinder.ai.lead.dispatch_messages import option_binds_no_step_message
from pathfinder.ai.lead.edit_messages import (
    changed_revision_message,
    delta_disagrees_with_the_strategy_message,
    edit_bound_nothing_message,
    edit_operation_refused_message,
    edit_work_order,
    no_strategy_to_edit_message,
    pending_changes_no_pass_accounted_for_message,
    unsupported_edit_message,
    wdk_refused_the_written_step_message,
)
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.pre_turn import hydrate_spec_from_the_strategy
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.strategy_refusals import wdk_refused_the_edit
from pathfinder.ai.tools.standalone.stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    fold_option_criteria,
    stated_wire_values,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import (
    CriterionChange,
    CriterionDisposition,
    SpecDiff,
    diff_specs,
)
from pathfinder.domain.strategy.spec_reconciliation import (
    spec_without_pending_analyses,
)
from pathfinder.domain.strategy.spec_to_operations import (
    criteria_the_edit_introduces,
    operations_for,
)
from pathfinder.domain.strategy.step_words import added_searches
from pathfinder.services.strategies.commit import (
    CommitResult,
    apply_operations_and_commit,
)
from pathfinder.services.strategies.graph_outcome import outcome_for_graph
from pathfinder.services.strategies.sync_state import ensure_sync_state

__all__ = ["edit_strategy", "run_edit"]


async def run_edit(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> EditDelta | SubAgentApprovalWait:
    """Run the edit and push it, on a fresh dispatch or a resumed one.

    A strategy that holds steps no spec states is edited from the spec those
    steps describe.
    """
    if resume is None:
        await hydrate_spec_from_the_strategy(deps.state, deps.runtime)
    record_the_spec_the_dispatch_found(deps, resume=resume)
    found = deps.state.domain.spec_before_dispatch
    graph = deps.runtime.strategy_session.get_graph(None)
    if found is None or not found.criteria or graph is None or not graph.steps:
        # Nothing has been written yet, so the refusal restores nothing: a spec
        # this turn framed for a fresh thread must survive a misrouted call.
        offered = tools_the_turn_offers(deps, ["frame_problem", "build_strategy"])
        raise ModelRetry(no_strategy_to_edit_message(offered))
    base_revision = strategy_revision(graph.to_strategy_ast())
    answered, pending = the_edit_the_strategy_owes(deps.state, found)
    frame = await run_frame(
        deps=deps,
        parent_tool_call_id=parent_tool_call_id,
        work_order=edit_work_order(
            reason,
            deps.state.user_prompt,
            found,
            pending=pending,
            answered=answered,
            answer=deps.state.turn_markers.answered,
        ),
        expected_criteria=len(found.criteria),
        resume=resume,
    )
    if isinstance(frame, SubAgentApprovalWait):
        return frame
    after = deps.state.domain.operational_spec
    if after is None or not after.criteria:
        refuse_and_restore(deps, edit_bound_nothing_message())
    # The draft before the fold is what this pass states: an option it absorbs
    # is a criterion the pass wrote, whatever carries its values.
    drafted = frozenset(criterion.id for criterion in after.criteria)
    # Both sides state an option as a value on the step that runs its search,
    # so the difference between them is a difference between steps. The stored
    # spec is what an earlier turn left, so only this turn's side is refused.
    before = fold_option_criteria(answered, live_step_ids=graph.steps).spec
    folded_after = fold_option_criteria(
        after,
        live_step_ids=graph.steps,
        answered_values=stated_wire_values(before),
    )
    if folded_after.unplaced:
        refuse_and_restore(
            deps, option_binds_no_step_message(folded_after.spec, folded_after.unplaced)
        )
    after = folded_after.spec
    # A criterion waiting for its analysis has no step to write; the EDA tools
    # add it, so the edit plans without it and the plan keeps it.
    planned = spec_without_pending_analyses(after)
    diff = diff_specs(before, planned)
    if frame.disposition != "spec_ready":
        return EditDelta(
            diff=diff,
            disposition="needs_user",
            summary=frame.summary,
            open_questions=list(frame.open_questions),
        )
    _refuse_a_pending_change_this_turn_did_not_account_for(
        deps, pending, frame.changes, drafted
    )
    return await _push_the_edit(
        deps=deps,
        after=after,
        planned=planned,
        diff=diff,
        graph=graph,
        base_revision=base_revision,
    )


async def _push_the_edit(
    *,
    deps: LeadDeps,
    after: OperationalSpec,
    planned: OperationalSpec,
    diff: SpecDiff,
    graph: StrategyGraph,
    base_revision: str,
) -> EditDelta:
    """Push what ``planned`` states; the thread's plan becomes ``after``."""
    try:
        ops = operations_for(diff, after=planned, graph=graph)
    except UnsupportedEditError as exc:
        refuse_and_restore(deps, unsupported_edit_message(str(exc)))
    except ApplyError as exc:
        refuse_and_restore(deps, edit_operation_refused_message(str(exc)))
    introduced = criteria_the_edit_introduces(after=planned, graph=graph)
    added = [c.id for c in planned.criteria if c.id in introduced]
    _refuse_a_delta_the_strategy_disagrees_with(deps, diff, added)
    # A criterion the strategy held no step for is one this edit builds, so it
    # carries no id from the previous turn to preserve.
    preserved = [
        c.criterion_id
        for c in diff.changes
        if c.disposition == "kept" and c.criterion_id in graph.steps
    ]
    if not ops:
        the_strategy_now_answers_to(deps.state, after, graph)
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
        refuse_and_restore(deps, edit_operation_refused_message(str(exc)))
    except ValidationError as exc:
        refuse_and_restore(
            deps,
            _refused_values_message(exc, diff=diff, after=planned, added=introduced),
        )
    outcome = _outcome_after_edit(agent_deps, commit)
    # The spec the thread carries states the option on the step that runs it,
    # exactly as the spec a build leaves behind does.
    deps.state.domain.operational_spec = after
    the_strategy_now_answers_to(
        deps.state, after, agent_deps.strategy_session.get_graph(None)
    )
    deps.state.record_build(outcome)
    searches = added_searches(planned, added)
    deps.state.turn_markers.record_added_searches(searches)
    _emit_graph_snapshot(agent_deps)
    # A push VEuPathDB did not take is the answer. The applied-operation line
    # would read as a success the strategy does not hold.
    refusal = wdk_refused_the_edit(commit)
    return EditDelta(
        diff=diff,
        description=commit.description if refusal is None else refusal.message,
        operations_applied=len(ops),
        added_step_ids=added,
        added_searches=searches,
        preserved_step_ids=preserved,
        dropped_step_ids=list(commit.dropped_step_ids),
        failed_step_ids=list(commit.failed_step_ids),
    )


def _refuse_a_pending_change_this_turn_did_not_account_for(
    deps: LeadDeps,
    pending: SpecDiff,
    declared: Sequence[CriterionChange],
    drafted: Collection[str],
) -> None:
    """Every unpushed change of an earlier pass needs this pass's disposition.

    A push carries them all, so one the pass never stated would reach the
    strategy with no account of it in the delta the reply is read from.
    """
    stated: dict[str, CriterionDisposition] = {
        change.criterion_id: change.disposition for change in declared
    }
    unaccounted = sorted(
        change.criterion_id
        for change in pending.changes
        if change.disposition != "kept"
        and not _accounts_for(change.criterion_id, stated, drafted)
    )
    if unaccounted:
        refuse_and_restore(
            deps, pending_changes_no_pass_accounted_for_message(unaccounted)
        )


def _accounts_for(
    criterion_id: str,
    stated: Mapping[str, CriterionDisposition],
    drafted: Collection[str],
) -> bool:
    """Whether the pass's word for this criterion agrees with what it drafted.

    A criterion the pass calls dropped is one its draft leaves out, and any
    other word is one its draft states. A word the draft contradicts accounts
    for nothing, because the two say different things about the same step.
    """
    disposition = stated.get(criterion_id)
    if disposition is None:
        return False
    return (disposition == "dropped") is (criterion_id not in drafted)


def _refuse_a_delta_the_strategy_disagrees_with(
    deps: LeadDeps, diff: SpecDiff, added: Collection[str]
) -> None:
    """The steps this edit builds are the criteria the diff calls added.

    The diff is the account the reply is read from, so a criterion the
    strategy builds and the account leaves out is a claim the researcher
    cannot check.
    """
    accounted = {c.criterion_id for c in diff.changes if c.disposition == "added"}
    disagreed = accounted.symmetric_difference(added)
    if disagreed:
        refuse_and_restore(
            deps, delta_disagrees_with_the_strategy_message(sorted(disagreed))
        )


_REFUSED_PARAMS = pydantic.TypeAdapter(list[ParamMessages])


def _params_wdk_named(exc: ValidationError) -> frozenset[str]:
    """The parameter names the refusal rows carry, empty when it carries none."""
    try:
        rows = _REFUSED_PARAMS.validate_python(exc.errors or [])
    except pydantic.ValidationError:
        return frozenset()
    return frozenset(row.param for row in rows)


def _steps_the_edit_writes(
    diff: SpecDiff, after: OperationalSpec, added: Collection[str]
) -> list[Criterion]:
    """The criteria whose values this edit sends to VEuPathDB.

    A criterion the edit builds a step for is written whatever the diff calls
    it, because the spec it is compared against already held it.
    """
    written = {
        change.criterion_id
        for change in diff.changes
        if change.disposition in {"added", "changed"}
    } | set(added)
    return [criterion for criterion in after.criteria if criterion.id in written]


def _refused_values_message(
    exc: ValidationError,
    *,
    diff: SpecDiff,
    after: OperationalSpec,
    added: Collection[str],
) -> str:
    """The refusal for values VEuPathDB turned down while the edit was pushed.

    The refused step is the one this edit writes that states a parameter the
    answer names; every written step is named when the answer names none.
    """
    params = _params_wdk_named(exc)
    written = _steps_the_edit_writes(diff, after, added)
    named = [c for c in written if not params.isdisjoint(c.resolved_params)]
    return wdk_refused_the_written_step_message(
        exc.detail or str(exc),
        steps=[f"[{c.id}] {c.search_name}" for c in (named or written)],
        params=sorted(params),
    )


def _outcome_after_edit(agent_deps: AgentDeps, commit: CommitResult) -> BuildOutcome:
    """The build the edit leaves behind, with the counts the commit wrote.

    The commit replaces every count with VEuPathDB's own before it returns, so
    the Lead reports the numbers the snapshot and the stored strategy carry.
    """
    session = agent_deps.strategy_session
    sync_state = ensure_sync_state(session)
    return outcome_for_graph(
        graph=session.get_graph(None),
        sync_state=sync_state,
        counts=sync_state.step_counts,
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

    The returned ``EditDelta`` carries the computed ``diff`` for this edit
    alone, measured against the spec the strategy answers to: every claim in
    your reply about what THIS edit kept, changed, added or dropped is read
    from it, and ``added_step_ids`` names the criteria it built a step for. A
    criterion framed on an earlier turn and built here reads as added in both.
    A claim about what the whole turn did to the spec it started from is read
    from ``ledger.frame.diff`` instead.
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
