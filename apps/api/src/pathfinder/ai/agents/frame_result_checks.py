"""What FRAME's result is held to inside its own run, before the dispatch reads it."""

from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.wdk import get_site_router

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_questions import questions_that_bind_to_nothing
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    numbered_requirements,
    reported_requirements,
    unknown_requirement_ids,
)


def hold_the_reports_to_the_requirement_list(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back, once per pass, a report that names a number the list lacks."""
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    held = state.stated_requirements
    unknown = unknown_requirement_ids(output.requirement_problems, held)
    if not unknown or state.unknown_requirements_sent_back:
        return output
    state.unknown_requirements_sent_back = True
    msg = (
        f"requirement_problems names {unknown}, and the list holds "
        f"{', '.join(numbered_requirements(held)) or 'none'}. A report names a "
        "requirement by its number in 'Requirements the researcher stated'. Use "
        "one of those numbers, or leave the entry out and say it in summary."
    )
    raise ModelRetry(msg)


def hold_the_questions_to_the_draft(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back, once per pass, a pass that asks about nothing its draft holds."""
    if not isinstance(output, FrameResult) or output.disposition != "needs_user":
        return output
    state = ctx.deps.agent_state
    if state.unbound_questions_sent_back:
        return output
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
    state.unbound_questions_sent_back = True
    raise ModelRetry(unbound)


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
    named = [
        report.site
        for report in output.requirement_problems
        if report.problem is RequirementProblem.ANOTHER_SITE_ANSWERS
        and report.site not in others
    ]
    if named:
        msg = (
            f"another_site_answers names {named}, which is no other site. Name one "
            f"of {', '.join(others)}, or bind the search this site holds."
        )
        raise ModelRetry(msg)
    return output


def hold_the_reports_to_the_refusals(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    """Send back a refusal of a search the site ran, and, once per pass, a
    missing search reported after the site refused one."""
    if not isinstance(output, FrameResult):
        return output
    state = ctx.deps.agent_state
    refused = state.refused_searches
    reports = output.requirement_problems
    unrefused = [
        r.search
        for r in reports
        if r.problem is RequirementProblem.SITE_REFUSED_THE_SEARCH
        and r.search not in refused
    ]
    if unrefused:
        named = ", ".join(refused) or "none"
        msg = (
            f"site_refused_the_search names {unrefused}, and this pass saw the "
            f"site refuse only {named}. Name a search the site refused."
        )
        raise ModelRetry(msg)
    missing = any(r.problem is RequirementProblem.SITE_HAS_NO_SEARCH for r in reports)
    if not refused or not missing or state.refusals_sent_back:
        return output
    state.refusals_sent_back = True
    answers = "; ".join(f"{name} ({answer})" for name, answer in refused.items())
    msg = (
        f"The site refused to run {answers} this pass. A requirement that search "
        "answers is site_refused_the_search with that search named in search, not "
        "site_has_no_search. Keep site_has_no_search for a requirement no search "
        "on this site answers."
    )
    raise ModelRetry(msg)


__all__ = [
    "hold_the_questions_to_the_draft",
    "hold_the_reports_to_the_refusals",
    "hold_the_reports_to_the_requirement_list",
    "hold_the_route_to_another_site",
]
