"""The Lead's FRAME dispatch tool, and the phase run behind it."""

from __future__ import annotations

from pydantic_ai import RunContext

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
    edit_message,
    framing_goal,
    message_asks,
    record_the_spec_the_dispatch_found,
    refuse_and_keep_what_it_bound,
    refuse_and_restore,
    the_edit_the_strategy_owes,
)
from pathfinder.ai.lead.dispatch_messages import (
    answered_question_work_order,
    asks_lines,
    earlier_turn_work_order,
    frame_bound_nothing_result,
    frame_claimed_more_than_it_bound,
    frame_result_from_draft,
    stopped_pass_work_order,
)
from pathfinder.ai.lead.edit_messages import edit_continuation_work_order
from pathfinder.ai.lead.frame_questions import questions_that_bind_to_nothing
from pathfinder.ai.lead.frame_requirements import (
    questions_for_the_card,
    requirements_the_site_lacks,
)
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_consult import card_questions
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.readings import count_readings
from pathfinder.ai.lead.site_routes import site_route_sentence
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
    Constraint,
    message_states,
)
from pathfinder.domain.strategy.named_groups import merged_scopes
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    numbered_requirements,
    record_roles,
    resolved_reports,
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
                spec,
                goal,
                message=state.user_prompt,
                brief=reason,
                asks=message_asks(deps),
            )
        return answered_question_work_order(
            spec,
            goal,
            answered.questions,
            answer=answered.answer,
            brief=reason,
            asks=message_asks(deps),
        )
    return "\n".join(
        [
            f"FRAME work order: {reason}",
            f"User's goal: {framing_goal(state)}",
            *asks_lines(message_asks(deps)),
            (
                "Operationalize into criteria, bind each to a real WDK search, "
                "resolve params, set the structure. Return a FrameResult."
            ),
        ]
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
    {
        PhaseStopReason.BUDGET,
        PhaseStopReason.TOOL_RETRIES,
        PhaseStopReason.PROVIDER,
        PhaseStopReason.SEARCH_NOT_SERVED,
    }
)


def _stop_to_continue(
    deps: LeadDeps, *, bound_before: int, draft: OperationalSpec
) -> PhaseStop | None:
    """The stop of a pass that is dispatched again rather than reported.

    A budget stop, a tool that refused every attempt, or a search the site does
    not serve, after the pass bound a criterion it did not start with has work
    left to continue, and the continuation is the system's to run. A pass that bound nothing repeats
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
            before, edit_message(deps), pending=pending, answered=answered, stop=stop
        )
    return stopped_pass_work_order(
        draft, deps.state.user_prompt, stop, asks=message_asks(deps)
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
        await count_readings(deps, result)
        lacking = requirements_the_site_lacks(deps, result)
        asked = questions_for_the_card(deps, result, lacking)
        deps.state.domain.record_questions(asked)
        deps.state.turn_markers.unstated_requirements = [
            c.requested_value for c in lacking
        ]
        reported = resolved_reports(result.requirement_problems, domain.requirements)
        domain.record_roles |= record_roles(result.record_types, domain.requirements)
        domain.group_scopes = merged_scopes(domain.group_scopes, result.group_scopes)
        domain.operational_spec = domain.follow_readings(
            domain.spec_before_dispatch, domain.operational_spec
        )
        return result.model_copy(
            update={"card_questions": card_questions(asked), "reported": reported}
        )
    return result


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
        agent_deps.agent_state.portal_route or _another_site_route(deps, delta),
    )


def _another_site_route(deps: LeadDeps, delta: FrameResult) -> str:
    """The sentence for the first requirement the pass reports another site
    answers, in the words the researcher stated it in."""
    routed = [
        report
        for report in delta.requirement_problems
        if report.problem is RequirementProblem.ANOTHER_SITE_ANSWERS
    ]
    if not routed:
        return ""
    stated = numbered_requirements(deps.state.domain.requirements).get(
        routed[0].requirement
    )
    if stated is None:
        return site_route_sentence(deps.site_id, routed[0].site)
    return site_route_sentence(
        deps.site_id,
        routed[0].site,
        f'whose searches state "{stated.requested_value}"',
    )


def _accepted(
    deps: LeadDeps, delta: FrameResult, draft: OperationalSpec, route: str
) -> FrameResult:
    """The result the Lead reads from a pass that answered, its changes read
    from the wire values, or a refusal. A pass sent to another site carries
    that site's sentence, alone when the pass changed nothing."""
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
    draft = _without_what_an_unbound_question_moved(deps, delta, draft)
    delta = delta.model_copy(update={"changes": derived_changes(found, draft)})
    _refuse_an_added_criterion_the_message_does_not_state(deps, found, draft)
    return delta


def _without_what_an_unbound_question_moved(
    deps: LeadDeps, delta: FrameResult, draft: OperationalSpec
) -> OperationalSpec:
    """The spec a pass leaves when it still ends on a question that binds nothing.

    The pass was told so inside its own run. Each criterion the dispatch found
    takes back the values it was found with, so the plan moves no built step
    before an answer; what the pass added or dropped stays.
    """
    found = deps.state.domain.spec_before_dispatch
    if (
        found is None
        or delta.disposition != "needs_user"
        or not questions_that_bind_to_nothing(
            delta, draft, found, lacking=requirements_the_site_lacks(deps, delta)
        )
    ):
        return draft
    as_found = {c.id: c for c in found.criteria}
    kept = draft.model_copy(
        update={
            "criteria": [
                as_found.get(c.id, c).model_copy(deep=True) for c in draft.criteria
            ]
        }
    )
    deps.state.domain.operational_spec = kept
    return kept


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
