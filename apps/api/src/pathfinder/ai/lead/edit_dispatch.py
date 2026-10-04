"""The Lead's edit dispatch: a delta over the strategy that already exists.

FRAME runs over the spec the dispatch found on the strategy, the two are
compared, and the difference is pushed as graph operations. A step the edit
does not name keeps its WDK id and every value the researcher set on it.
"""

from __future__ import annotations

from collections.abc import Collection

import pydantic
from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry, ToolFailed
from veupathdb.errors import ParamMessages, ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.answered_strategy import the_strategy_now_answers_to
from pathfinder.ai.lead.deleted_steps import named_step
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    record_the_spec_the_dispatch_found,
    refuse_and_restore,
    refuse_without_retry,
    the_edit_the_strategy_owes,
)
from pathfinder.ai.lead.dispatch_messages import option_binds_no_step_message
from pathfinder.ai.lead.edit_messages import (
    changed_revision_message,
    delta_disagrees_with_the_strategy_message,
    edit_bound_nothing_message,
    edit_operation_refused_message,
    edit_work_order,
    no_earlier_revision_message,
    no_strategy_to_edit_message,
    nothing_to_undo_message,
    removal_is_the_cards_message,
    undo_moves_nothing_message,
    unsupported_edit_message,
    wdk_refused_the_written_step_message,
)
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.pre_turn import hydrate_spec_from_the_strategy, stated_spec_of
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.strategy_refusals import wdk_refused_the_edit
from pathfinder.ai.tools.standalone.stream_parts import graph_snapshot_chunk
from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.orthology import organism_move_refusal
from pathfinder.domain.strategy.revision import parse_strategy_ast, strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import (
    SpecDiff,
    diff_specs,
    steps_only_removed,
)
from pathfinder.domain.strategy.spec_fold import (
    fold_option_criteria,
    stated_wire_values,
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
    apply_operations_and_commit,
)
from pathfinder.services.strategies.data_marks import read_data_marks
from pathfinder.services.strategies.graph_outcome import live_outcome
from pathfinder.services.strategies.revision_ops import previous_revision

__all__ = ["edit_strategy", "run_edit"]

_UNDONE = "The strategy is back to the revision before the last change."


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
    if resume is None and deps.intent is not None and deps.intent.asks_only_to_undo():
        return await _undo(deps=deps, graph=graph, base_revision=base_revision)
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
        # Nothing is pushed before the answer, so the delta carries no diff: a
        # row that read "changed" would state a change the strategy does not hold.
        asked = {q.prompt for q in frame.card_questions}
        return EditDelta(
            diff=SpecDiff(),
            disposition="needs_user",
            summary=frame.summary,
            open_questions=[
                q for q in deps.state.domain.open_questions if q.question in asked
            ],
            card_questions=frame.card_questions,
            pending_step_ids=[
                c.criterion_id
                for c in diff.changes
                if c.disposition in {"added", "changed"}
            ],
        )
    _refuse_a_removal_the_card_owns(deps, diff, graph)
    moved = organism_move_refusal(
        "other" if deps.intent is None else deps.intent.edit_direction,
        before=before,
        after=planned,
    )
    if moved is not None:
        refuse_and_restore(deps, moved)
    return await _push_the_edit(
        deps=deps,
        after=after,
        diff=diff,
        graph=graph,
        base_revision=base_revision,
        undo=False,
    )


async def _undo(
    *, deps: LeadDeps, graph: StrategyGraph, base_revision: str
) -> EditDelta:
    """Return the strategy to the revision before its last change.

    Both trees are stated the same way, so the diff holds only what the last
    change moved.
    """
    async with deps.runtime.db_session_factory() as session:
        revision = await previous_revision(
            session, conversation_id=deps.state.conversation_id
        )
    stored = None if revision is None else parse_strategy_ast(revision.strategy_ast)
    live = graph.to_strategy_ast()
    if revision is None or stored is None or live is None:
        raise ToolFailed(no_earlier_revision_message())
    if revision.revision == base_revision:
        raise ToolFailed(nothing_to_undo_message())
    site_id, goal = deps.runtime.site_id, deps.state.user_prompt
    before = await stated_spec_of(live, site_id=site_id, goal=goal)
    after = await stated_spec_of(stored, site_id=site_id, goal=goal)
    diff = diff_specs(before, after)
    _refuse_a_removal_the_card_owns(deps, diff, graph)
    # The commit's guards read the spec the thread states, so it states the
    # restored tree before the push.
    deps.state.domain.operational_spec = after
    return await _push_the_edit(
        deps=deps,
        after=after,
        diff=diff,
        graph=graph,
        base_revision=base_revision,
        undo=True,
    )


async def _push_the_edit(
    *,
    deps: LeadDeps,
    after: OperationalSpec,
    diff: SpecDiff,
    graph: StrategyGraph,
    base_revision: str,
    undo: bool,
) -> EditDelta:
    """Push what ``after`` states with no criterion that waits for its
    analysis; the thread's plan becomes ``after``.

    ``undo`` says the edit returns to the previous revision, which an empty
    batch cannot do.
    """
    planned = spec_without_pending_analyses(after)
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
    if not ops and undo:
        refuse_without_retry(deps, undo_moves_nothing_message())
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
    outcome = live_outcome(agent_deps.strategy_session, commit.failed_step_ids)
    # The spec the thread carries states the option on the step that runs it,
    # exactly as the spec a build leaves behind does.
    deps.state.domain.operational_spec = after
    deps.state.domain.data_marks = await read_data_marks(agent_deps.site_id, [after])
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
        summary=_UNDONE if undo and refusal is None else "",
        description=commit.description if refusal is None else refusal.message,
        operations_applied=len(ops),
        added_step_ids=added,
        added_searches=searches,
        preserved_step_ids=preserved,
        dropped_step_ids=list(commit.dropped_step_ids),
        failed_step_ids=list(commit.failed_step_ids),
    )


def _refuse_a_removal_the_card_owns(
    deps: LeadDeps, diff: SpecDiff, graph: StrategyGraph
) -> None:
    removed = steps_only_removed(diff, graph.steps)
    if removed:
        refuse_and_restore(
            deps,
            removal_is_the_cards_message(
                {sid: named_step(graph.steps[sid]) for sid in removed}
            ),
        )


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


def _unbound(deps: LeadDeps, reason: str, refusal: str) -> EditDelta:
    """The edit no pass may retry, with the refusal that stopped it as a fact."""
    unbound = (
        f"The edit was not applied: {reason} The planning pass refused it: {refusal}"
    )
    deps.state.turn_markers.unbound_edit = unbound
    return EditDelta(diff=SpecDiff(), disposition="unbound", summary=unbound)


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
    edit. A request to undo the last change is an edit too: it returns the
    strategy to the revision before that change and frames nothing.

    ``reason`` is what the request changes, in one sentence.

    The returned ``EditDelta`` carries the computed ``diff`` for this edit
    alone, measured against the spec the strategy answers to: every claim in
    your reply about what THIS edit kept, changed, added or dropped is read
    from it, and ``added_step_ids`` names the criteria it built a step for. A
    criterion framed on an earlier turn and built here reads as added in both.
    A claim about what the whole turn did to the spec it started from is read
    from ``ledger.frame.diff`` instead. Disposition ``needs_user`` pushed
    nothing: its ``diff`` is empty and ``pending_step_ids`` names the criteria
    the plan moved, which the strategy does not hold until the answer. Disposition
    ``unbound`` ends the edit: nothing was applied, and the reply names what
    could not be bound.
    """
    tool_call_id = dispatch_call_id(ctx)
    try:
        result = await run_edit(
            deps=ctx.deps,
            parent_tool_call_id=tool_call_id,
            reason=reason,
        )
    except ModelRetry as refused:
        if not ctx.last_attempt:
            raise
        return _unbound(ctx.deps, reason, refused.message)
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
    return result
