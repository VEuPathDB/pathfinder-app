"""What FRAME's result is held to inside its own run, before the dispatch reads it."""

from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.wdk import get_site_router

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.ai.lead.frame_questions import questions_that_bind_to_nothing
from pathfinder.domain.strategy.constraints import CONSTRAINT_KINDS
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
    numbered_requirements,
    record_types_without_a_role,
    reported_requirements,
    unknown_requirement_ids,
)


def _without(output: FrameResult, dropped: list[RequirementReport]) -> FrameResult:
    return output.model_copy(
        update={
            "requirement_problems": [
                r for r in output.requirement_problems if r not in dropped
            ]
        }
    )


def hold_the_reports_to_the_requirement_list(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back a report that names a number the list lacks."""
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    held = state.stated_requirements
    unknown = unknown_requirement_ids(output.requirement_problems, held)
    if not unknown:
        return output
    if not may_refuse(ctx, state.refusals):
        dropped = [r for r in output.requirement_problems if r.requirement in unknown]
        return _without(output, dropped).with_gap(
            "report_dropped",
            f"The pass reported {unknown}, which the requirement list does not hold.",
        )
    state.refusals += 1
    msg = (
        f"requirement_problems names {unknown}, and the list holds "
        f"{', '.join(numbered_requirements(held)) or 'none'}. A report names a "
        "requirement by its number in 'Requirements the researcher stated'. Use "
        "one of those numbers, or leave the entry out and say it in summary."
    )
    raise ModelRetry(msg)


def hold_the_record_types_to_a_role(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    unroled = record_types_without_a_role(
        output.record_types, state.stated_requirements, state.held_record_roles
    )
    if not unroled:
        return output
    if not may_refuse(ctx, state.refusals):
        return output.with_gaps(
            [
                PassGap(
                    kind="record_role_missing",
                    sentence=(
                        f"The pass stated no role for the record type "
                        f"{c.requested_value!r}, so it is judged as the class the "
                        f"result must be."
                    ),
                )
                for c in unroled.values()
            ]
        )
    state.refusals += 1
    msg = (
        f"record_types states no role for {', '.join(unroled)}. Give each "
        "record-type requirement in 'Requirements the researcher stated' a role: "
        "answer when the result is those records, through when the tree passes "
        "through them."
    )
    raise ModelRetry(msg)


def hold_the_questions_to_the_draft(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back a pass that asks about nothing its draft holds."""
    if not isinstance(output, FrameResult) or output.disposition != "needs_user":
        return output
    state = ctx.deps.agent_state
    unbound = questions_that_bind_to_nothing(
        output,
        state.operational_spec_draft,
        state.spec_the_dispatch_found,
        lacking=reported_requirements(
            output.requirement_problems,
            state.stated_requirements,
            RequirementProblem.SITE_HAS_NO_SEARCH,
        ),
    )
    if not unbound:
        return output
    if not may_refuse(ctx, state.refusals):
        return output.with_gap(
            "questions_bind_nothing",
            "The pass asks questions whose answers bind nothing its draft holds.",
        )
    state.refusals += 1
    raise ModelRetry(unbound)


def hold_the_questions_to_a_dimension(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back a pass that stops on the user with a question that decides nothing."""
    if not isinstance(output, FrameResult):
        return output
    undecided = output.undecided_questions
    if not undecided:
        return output
    state = ctx.deps.agent_state
    if not may_refuse(ctx, state.refusals):
        return output.with_gap(
            "question_decides_nothing",
            f"These questions name no dimension and recommend no value: {undecided}.",
        )
    state.refusals += 1
    msg = (
        f"These open questions decide nothing: {undecided}. Give each "
        f"one the `dimension` its open parameter states, one of "
        f"{CONSTRAINT_KINDS}, and the `recommended_value` you would "
        f"use if the user does not answer."
    )
    raise ModelRetry(msg)


def hold_the_route_to_another_site(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back a report that routes to no site, or to this conversation's own."""
    if not isinstance(output, FrameResult):
        return output
    others = sorted(
        site.id
        for site in get_site_router().list_sites()
        if site.id != ctx.deps.site_id
    )
    unrouted = [
        report
        for report in output.requirement_problems
        if report.problem is RequirementProblem.ANOTHER_SITE_ANSWERS
        and report.site not in others
    ]
    if not unrouted:
        return output
    named = [report.site for report in unrouted]
    state = ctx.deps.agent_state
    if not may_refuse(ctx, state.refusals):
        return _without(output, unrouted).with_gap(
            "report_dropped",
            f"The pass named {named} as another site that answers, and none is one.",
        )
    state.refusals += 1
    msg = (
        f"another_site_answers names {named}, which is no other site. Name one "
        f"of {', '.join(others)}, or bind the search this site holds."
    )
    raise ModelRetry(msg)


def _misreported_refusals(
    reports: list[RequirementReport], state: AgentToolState
) -> tuple[list[RequirementReport], str]:
    refused = state.refused_searches
    unrefused = [
        r
        for r in reports
        if r.problem is RequirementProblem.SITE_REFUSED_THE_SEARCH
        and r.search not in refused
    ]
    unnamed = [r for r in unrefused if not r.search]
    if unnamed:
        return unnamed, (
            f"site_refused_the_search for {[r.requirement for r in unnamed]} names "
            "no search: put the search the site refused in `search`, or report the "
            "requirement as site_has_no_search."
        )
    unlisted = [r for r in unrefused if r.search in state.unserved_searches]
    if unlisted:
        return unlisted, (
            f"site_refused_the_search names {[r.search for r in unlisted]}, which "
            "the site's catalog lists under no record type. A requirement no "
            "search on this site answers is site_has_no_search."
        )
    if refused and unrefused:
        return unrefused, (
            f"site_refused_the_search names {[r.search for r in unrefused]}, and "
            f"this pass saw the site refuse only {', '.join(refused)}. Name one of "
            "those, or report the requirement as site_has_no_search."
        )
    return [], ""


def hold_the_reports_to_the_refusals(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back a refusal of a search the site ran, and a missing search
    reported after the site refused one."""
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    refused = state.refused_searches
    reports = output.requirement_problems
    misreported, change = _misreported_refusals(reports, state)
    if misreported:
        if not may_refuse(ctx, state.refusals):
            return _without(output, misreported).with_gap(
                "report_dropped",
                f"The pass reported the site refused "
                f"{[r.search for r in misreported]}, and it did not this pass.",
            )
        state.refusals += 1
        raise ModelRetry(change)
    missing = any(r.problem is RequirementProblem.SITE_HAS_NO_SEARCH for r in reports)
    if not refused or not missing:
        return output
    if not may_refuse(ctx, state.refusals):
        return output.with_gap(
            "missing_after_refusal",
            f"The pass reports a requirement no search answers after the site "
            f"refused {', '.join(refused)} this pass.",
        )
    state.refusals += 1
    answers = "; ".join(f"{name} ({answer})" for name, answer in refused.items())
    msg = (
        f"The site refused to run {answers} this pass. A requirement that search "
        "answers is site_refused_the_search with that search named in search, not "
        "site_has_no_search. Keep site_has_no_search for a requirement no search "
        "on this site answers."
    )
    raise ModelRetry(msg)


__all__ = [
    "hold_the_questions_to_a_dimension",
    "hold_the_questions_to_the_draft",
    "hold_the_record_types_to_a_role",
    "hold_the_reports_to_the_refusals",
    "hold_the_reports_to_the_requirement_list",
    "hold_the_route_to_another_site",
]
