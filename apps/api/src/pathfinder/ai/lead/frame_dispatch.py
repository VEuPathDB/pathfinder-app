"""The Lead's FRAME dispatch tool, and the phase run behind it."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai import RunContext

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    framing_goal,
    record_the_spec_the_dispatch_found,
    refuse_and_keep_what_it_bound,
    refuse_and_restore,
    the_edit_the_strategy_owes,
)
from pathfinder.ai.lead.dispatch_messages import (
    answered_question_work_order,
    earlier_turn_work_order,
    frame_bound_nothing_result,
    frame_claimed_more_than_it_bound,
    frame_result_from_draft,
    stopped_pass_work_order,
)
from pathfinder.ai.lead.edit_messages import edit_continuation_work_order
from pathfinder.ai.lead.frame_questions import questions_that_bind_to_nothing
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_consult import card_questions
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
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
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintSource,
    ConstraintStatus,
    message_states,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import (
    unanswered_questions,
    with_withdrawals,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, diff_specs


def frame_work_order(reason: str, deps: LeadDeps) -> str:
    """The order FRAME runs, naming the whole request the turn answers.

    A draft that holds bound criteria and no strategy on the site is work an
    earlier pass left, so the order continues it instead of framing the goal
    again.
    """
    state = deps.state
    spec = state.domain.operational_spec
    if spec is not None and _continues_the_draft(deps, spec):
        goal = spec.goal or framing_goal(state)
        answered = state.turn_markers.answered
        if answered is None:
            return earlier_turn_work_order(
                spec, goal, message=state.user_prompt, brief=reason
            )
        return answered_question_work_order(
            spec, goal, answered.questions, answer=answered.answer, brief=reason
        )
    return (
        f"FRAME work order: {reason}\n"
        f"User's goal: {framing_goal(state)}\n"
        "Operationalize into criteria, bind each to a real WDK search, resolve "
        "params, set the structure. Return a FrameResult."
    )


def _bound_count(spec: OperationalSpec) -> int:
    return sum(1 for c in spec.criteria if c.bound)


def _continues_the_draft(deps: LeadDeps, spec: OperationalSpec) -> bool:
    """Whether a pass over this spec continues it rather than framing afresh.

    A new request sets the draft aside, except after a card answered a
    question that a pass under the same request asked.
    """
    if not _bound_count(spec) or deps.step_count > 0:
        return False
    answered = deps.state.turn_markers.answered
    if answered is not None and answered.on_card:
        return True
    intent = deps.intent
    return (
        intent is None or intent.classification is not IntentClassification.NEW_STRATEGY
    )


# A repeated call is a loop the guard ended, so it is never continued.
_CONTINUED_STOPS = frozenset(
    {PhaseStopReason.BUDGET, PhaseStopReason.TOOL_RETRIES, PhaseStopReason.PROVIDER}
)


def _stop_to_continue(
    deps: LeadDeps, *, bound_before: int, draft: OperationalSpec
) -> PhaseStop | None:
    """The stop of a pass that is dispatched again rather than reported.

    A budget stop, or a tool that refused every attempt, after the pass bound
    a criterion it did not start with has work left to continue, and the
    continuation is the system's to run. A pass that bound nothing repeats
    itself, so the Lead hears about it instead. A request the provider did not
    complete is no fault of the pass, so it is continued whatever it bound.
    """
    stop = deps.last_phase_stop
    if stop is None or stop.reason not in _CONTINUED_STOPS:
        return None
    if deps.frame_retried_after_stop:
        return None
    if (
        stop.reason is not PhaseStopReason.PROVIDER
        and _bound_count(draft) <= bound_before
    ):
        return None
    return stop


def _continuation_work_order(
    deps: LeadDeps, work_order: str, draft: OperationalSpec, stop: PhaseStop
) -> str:
    """What the continuing pass is asked to do, in the shape the turn owes.

    A pass that continued the draft runs its own order again, so the answer it
    resolves reaches the retry. An edit of a strategy that holds steps owes a
    disposition per criterion, so its continuation is an edit work order.
    """
    before = deps.state.domain.spec_before_dispatch
    if before is not None and _continues_the_draft(deps, before):
        return work_order
    if before is not None and before.criteria and deps.step_count > 0:
        answered, pending = the_edit_the_strategy_owes(deps.state, before)
        return edit_continuation_work_order(
            before,
            deps.state.user_prompt,
            pending=pending,
            answered=answered,
            answer=deps.state.turn_markers.answered,
            stop=stop,
        )
    return stopped_pass_work_order(draft, deps.state.user_prompt, stop)


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
    is one the result the Lead is given asks. The card offers to withdraw each
    requirement the researcher stated that no search states, and asks no
    question the researcher answered or whose only option binds a value the
    spec already holds.
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
        domain = deps.state.domain
        asked = unanswered_questions(
            with_withdrawals(
                result.questions(domain.operational_spec),
                _unstated_requirements(deps, result.unstated),
            ),
            answered=[q.question for q in domain.answered_questions],
        )
        deps.state.domain.record_questions(asked)
        deps.state.turn_markers.unstated_requirements = list(result.unstated)
        return result.model_copy(update={"card_questions": card_questions(asked)})
    return result


def _unstated_requirements(deps: LeadDeps, named: Sequence[str]) -> list[Constraint]:
    """The held requirements the researcher stated that no search of the spec
    states: each one the ledger lists as ungroundable, and each one the pass
    names in ``unstated`` that is no scope every search runs in."""
    held = {c.key for c in deps.state.domain.requirements}
    return [
        g.constraint
        for g in derive_ledger(deps.state, deps.intent).constraints.grounded
        if g.constraint.source is ConstraintSource.USER_EXPLICIT
        and g.constraint.key in held
        and (
            g.status is ConstraintStatus.UNGROUNDABLE
            or (
                g.constraint.kind not in STRATEGY_SCOPES
                and any(_names_the_requirement(text, g.constraint) for text in named)
            )
        )
    ]


def _names_the_requirement(text: str, requirement: Constraint) -> bool:
    """Whether the words carry each other: one requirement, in either phrasing."""
    value = requirement.requested_value
    return message_states(text, value) or message_states(value, text)


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
        draft = agent_deps.agent_state.operational_spec_draft
        stop = _stop_to_continue(deps, bound_before=bound_before, draft=draft)
        if stop is not None:
            deps.frame_retried_after_stop = True
            # The continuation belongs to the dispatch that stopped, so the
            # spec it found stays the one recorded at that dispatch's start.
            return await _run_frame(
                deps=deps,
                parent_tool_call_id=parent_tool_call_id,
                work_order=_continuation_work_order(deps, work_order, draft, stop),
                expected_criteria=expected_criteria,
            )
        return frame_result_from_draft(
            deps.state.domain.operational_spec, deps.last_phase_stop
        )
    return _accepted(
        deps,
        delta,
        agent_deps.agent_state.operational_spec_draft,
        agent_deps.agent_state.portal_route,
    )


def _accepted(
    deps: LeadDeps, delta: FrameResult, draft: OperationalSpec, route: str
) -> FrameResult:
    """The result the Lead reads from a pass that answered, its changes read
    from the wire values, or a refusal. A pass sent to the portal carries the
    portal's sentence, alone when the pass changed nothing."""
    found = deps.state.domain.spec_before_dispatch
    if route and draft == (found or OperationalSpec(goal=draft.goal)):
        return FrameResult(disposition="needs_user", summary=route)
    if route:
        delta = delta.model_copy(update={"summary": f"{route} {delta.summary}"})
    if delta.disposition == "spec_ready" and not any(
        c.bound or c.pending_analysis for c in draft.criteria
    ):
        if deps.empty_frame_reported:
            return frame_bound_nothing_result()
        deps.empty_frame_reported = True
        refuse_and_restore(deps, frame_claimed_more_than_it_bound(delta.summary))
    delta = delta.model_copy(update={"changes": derived_changes(found, draft)})
    _refuse_questions_that_bind_to_nothing(deps, delta, draft)
    _refuse_an_unstated_requirement_the_researcher_did_not_write(deps, delta)
    _refuse_an_added_criterion_the_message_does_not_state(deps, found, draft)
    return delta


def derived_changes(
    found: OperationalSpec | None, draft: OperationalSpec
) -> list[CriterionChange]:
    """What the pass did to each criterion the dispatch found, read from the
    wire values of the two specs. A drop carries the reason the pass gave."""
    if found is None or not found.criteria:
        return []
    reasons = {d.text: d.reason for d in draft.dropped}
    texts = {c.id: c.text for c in found.criteria}
    return [
        change.model_copy(
            update={"reason": reasons.get(texts[change.criterion_id], "")}
        )
        if change.disposition == "dropped"
        else change
        for change in diff_specs(found, draft).changes
        if change.criterion_id in texts
    ]


def unwritten_requirements_refusal(unwritten: list[str]) -> str:
    """Why a pass whose unstated list names entries no message of the researcher
    states is refused, with both ways to correct an entry."""
    return (
        f"unstated names {unwritten}, which no message of the researcher states. "
        "Each entry is a requirement of the request that no search on the site "
        "states, in the words the researcher wrote it in. Restate a requirement "
        "in those words, and remove an entry that names no requirement of the "
        "request, such as a note about a count, the build or a later step."
    )


def _refuse_an_unstated_requirement_the_researcher_did_not_write(
    deps: LeadDeps, delta: FrameResult
) -> None:
    """Refuse a pass that names a requirement no message of the researcher states."""
    messages = deps.state.researcher_messages()
    unwritten = [
        text
        for text in delta.unstated
        if not any(message_states(message, text) for message in messages)
    ]
    if unwritten:
        refuse_and_keep_what_it_bound(deps, unwritten_requirements_refusal(unwritten))


def _refuse_an_added_criterion_the_message_does_not_state(
    deps: LeadDeps, found: OperationalSpec | None, draft: OperationalSpec
) -> None:
    """Refuse an edit pass that adds a criterion no requirement of the message
    states. An edit changes what the message asks for, and a question is
    answered without a step."""
    intent = deps.intent
    if intent is None or found is None or deps.step_count == 0:
        return
    message = deps.state.user_prompt
    rest = message.casefold()
    for ask in intent.researcher_asks(message):
        rest = rest.replace(ask.text.casefold(), " ")
    held = {c.id for c in found.criteria}
    for criterion in draft.criteria:
        if criterion.id in held or message_states(rest, criterion.text):
            continue
        if any(
            _names_the_requirement(criterion.text, c)
            for c in intent.explicit_constraints
        ):
            continue
        refuse_and_keep_what_it_bound(
            deps,
            f"The pass adds '{criterion.id}' ('{criterion.text}'), which no "
            "requirement of the message states; a question is answered with "
            "compare_search_variants, not with a step. Drop it, or name the "
            "requirement the message states for it.",
            refused={criterion.id},
        )


def _refuse_questions_that_bind_to_nothing(
    deps: LeadDeps, delta: FrameResult, draft: OperationalSpec
) -> None:
    """Refuse once a pass that asks about a criterion its draft does not hold.

    The answer to such a question lands nowhere, so the turn that follows has
    nothing to build from it. The retry keeps what the pass bound.
    """
    if delta.disposition != "needs_user" or deps.unbound_questions_reported:
        return
    unbound = questions_that_bind_to_nothing(
        delta, draft, deps.state.domain.spec_before_dispatch
    )
    if unbound:
        deps.unbound_questions_reported = True
        refuse_and_keep_what_it_bound(deps, unbound)


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
    sized below what the conversation already states, so a count below the evidence
    is raised to it.

    Available once per turn, while the strategy holds no step. A strategy
    that holds one is changed with ``edit_strategy``."""
    tool_call_id = dispatch_call_id(ctx)
    result = await run_frame(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        work_order=frame_work_order(reason, ctx.deps),
        expected_criteria=expected_criteria,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
        return result
    ctx.deps.state.turn_markers.framed = True
    return result
