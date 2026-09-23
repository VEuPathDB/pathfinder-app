"""The Lead's FRAME dispatch tool, and the phase run behind it."""

from __future__ import annotations

from pydantic_ai import RunContext

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    framing_goal,
    record_the_spec_the_dispatch_found,
    refuse_and_restore,
)
from pathfinder.ai.lead.dispatch_messages import (
    ContinuationReason,
    frame_bound_nothing_result,
    frame_claimed_more_than_it_bound,
    frame_continuation_work_order,
    frame_result_from_draft,
    questions_that_bind_to_nothing,
    undeclared_spec_changes,
)
from pathfinder.ai.lead.edit_messages import edit_continuation_work_order
from pathfinder.ai.lead.phase_stop import PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from pathfinder.ai.lead.sub_agent_tools import (
    LeadDeps,
    apply_agent_state,
    criteria_floor,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.spec_diff import diff_specs


def frame_work_order(reason: str, state: PipelineState) -> str:
    """The order FRAME runs, naming the whole request the turn answers.

    A draft that holds bound criteria and no built strategy is work an earlier
    pass left, so the order continues it instead of framing the goal again.
    """
    domain = state.domain
    spec = domain.operational_spec
    if spec is not None and _bound_count(spec) and domain.last_build_outcome is None:
        answered = state.turn_markers.answered_questions
        return frame_continuation_work_order(
            spec,
            spec.goal or framing_goal(state),
            ContinuationReason.ANSWERED_QUESTION
            if answered
            else ContinuationReason.EARLIER_TURN,
            answered=answered,
            message=state.user_prompt,
            brief=reason,
        )
    return (
        f"FRAME work order: {reason}\n"
        f"User's goal: {framing_goal(state)}\n"
        "Operationalize into criteria, bind each to a real WDK search, resolve "
        "params, set the structure. Return a FrameResult."
    )


def _bound_count(spec: OperationalSpec | None) -> int:
    return sum(1 for c in spec.criteria if c.bound) if spec is not None else 0


def _continue_the_stopped_pass(
    deps: LeadDeps, *, bound_before: int, draft: OperationalSpec
) -> bool:
    """Whether a stopped pass is dispatched again rather than reported.

    A budget stop that bound a criterion the pass did not start with has work
    left to continue, and the continuation is the system's to run. A pass that
    bound nothing repeats itself, so the Lead hears about it instead.
    """
    stop = deps.last_phase_stop
    if stop is None or stop.reason is not PhaseStopReason.BUDGET:
        return False
    if deps.frame_retried_after_stop:
        return False
    return _bound_count(draft) > bound_before


def _continuation_work_order(deps: LeadDeps) -> str:
    """What the continuing pass is asked to do, in the shape the turn owes.

    A turn that started from a strategy owes a disposition per criterion, so
    its continuation is an edit work order.
    """
    before = deps.state.domain.spec_before_dispatch
    if before is not None and before.criteria:
        return edit_continuation_work_order(before, deps.state.user_prompt)
    return frame_continuation_work_order(
        deps.state.domain.operational_spec,
        deps.state.user_prompt,
        ContinuationReason.BUDGET_STOP,
    )


async def run_frame(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    work_order: str,
    expected_criteria: int = 3,
    resume: SubAgentResume | None = None,
) -> FrameResult | SubAgentApprovalWait:
    """Run FRAME and record the questions its result leaves for the user.

    A refused pass raises before the record, so every question the thread holds
    is one the result the Lead is given asks.
    """
    record_the_spec_the_dispatch_found(deps, resume=resume)
    result = await _run_frame(
        deps=deps,
        parent_tool_call_id=parent_tool_call_id,
        work_order=work_order,
        expected_criteria=expected_criteria,
        resume=resume,
    )
    if isinstance(result, FrameResult):
        deps.state.domain.record_questions(result.open_questions)
    return result


async def _run_frame(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    work_order: str,
    expected_criteria: int = 3,
    resume: SubAgentResume | None = None,
) -> FrameResult | SubAgentApprovalWait:
    """Run FRAME and apply its result, on a fresh dispatch or a resumed one."""
    agent_deps = agent_deps_for(deps)
    if not agent_deps.agent_state.operational_spec_draft.goal:
        agent_deps.agent_state.operational_spec_draft.goal = deps.state.user_prompt
    bound_before = _bound_count(agent_deps.agent_state.operational_spec_draft)
    delta = await stream_sub_agent(
        run=PhaseRun(
            "frame",
            work_order,
            max(expected_criteria, criteria_floor(deps.state)),
        ),
        agent_deps=agent_deps,
        parent_tool_call_id=parent_tool_call_id,
        expected_output_type=FrameResult,
        deps=deps,
        resume=resume,
    )
    if isinstance(delta, SubAgentApprovalWait):
        return delta
    apply_agent_state(deps, agent_deps)
    if delta is None:
        if _continue_the_stopped_pass(
            deps,
            bound_before=bound_before,
            draft=agent_deps.agent_state.operational_spec_draft,
        ):
            deps.frame_retried_after_stop = True
            # The continuation belongs to the dispatch that stopped, so the
            # spec it found stays the one recorded at that dispatch's start.
            return await _run_frame(
                deps=deps,
                parent_tool_call_id=parent_tool_call_id,
                work_order=_continuation_work_order(deps),
                expected_criteria=expected_criteria,
            )
        return frame_result_from_draft(deps.state.domain.operational_spec)
    draft = agent_deps.agent_state.operational_spec_draft
    if delta.disposition == "spec_ready" and not any(c.bound for c in draft.criteria):
        if deps.empty_frame_reported:
            return frame_bound_nothing_result()
        deps.empty_frame_reported = True
        refuse_and_restore(deps, frame_claimed_more_than_it_bound(delta.summary))
    _refuse_questions_that_bind_to_nothing(deps, delta, draft)
    before = deps.state.domain.spec_before_dispatch
    if before is not None and before.criteria:
        problem = undeclared_spec_changes(
            diff_specs(before, draft), delta.changes, before
        )
        if problem:
            refuse_and_restore(deps, problem)
    return delta


def _refuse_questions_that_bind_to_nothing(
    deps: LeadDeps, delta: FrameResult, draft: OperationalSpec
) -> None:
    """Refuse once a pass that asks about a criterion its draft does not hold.

    The answer to such a question lands nowhere, so the turn that follows has
    nothing to build from it.
    """
    if delta.disposition != "needs_user" or deps.unbound_questions_reported:
        return
    unbound = questions_that_bind_to_nothing(
        delta.open_questions, draft, deps.state.domain.spec_before_dispatch
    )
    if unbound:
        deps.unbound_questions_reported = True
        refuse_and_restore(deps, unbound)


async def frame_problem(
    ctx: RunContext[LeadDeps], reason: str, expected_criteria: int = 3
) -> FrameResult:
    """Run the FRAME sub-agent: operationalize the goal into a realizable
    OperationalSpec - criteria bound to real WDK searches with auto-resolved
    params + a combine structure. Call this FIRST, then ``build_strategy``.
    Returns a ``FrameResult`` (disposition ``needs_user`` when criteria have
    open param slots the user must fill).

    ``expected_criteria`` is how many distinct filters the goal states - count
    the "and"s in the request. It sizes FRAME's tool budget, so undercounting a
    large request makes it run out before it binds them all. The pass is never
    sized below what the thread already states, so a count below the evidence
    is raised to it.

    Available once per turn, while the thread has no strategy to change with
    ``edit_strategy`` and no empty build waiting on the user."""
    tool_call_id = dispatch_call_id(ctx)
    result = await run_frame(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        work_order=frame_work_order(reason, ctx.deps.state),
        expected_criteria=expected_criteria,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
        return result
    ctx.deps.state.turn_markers.framed = True
    return result
