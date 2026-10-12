"""What FRAME's result is held to inside its own run, before the dispatch reads it."""

from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

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


__all__ = [
    "hold_the_questions_to_the_draft",
    "hold_the_reports_to_the_requirement_list",
]
