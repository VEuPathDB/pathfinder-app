"""The held requirements a framing pass reports the site has no search for."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    reported_requirements,
)


def requirements_the_site_lacks(
    deps: LeadDeps, result: FrameResult
) -> list[Constraint]:
    """The held requirements the pass reports no search on the site can answer."""
    return reported_requirements(
        result.requirement_problems,
        deps.state.domain.requirements,
        RequirementProblem.SITE_HAS_NO_SEARCH,
    )


def requirements_no_search_states(
    deps: LeadDeps, lacking: Sequence[Constraint]
) -> list[Constraint]:
    """The held requirements the researcher stated that no search of the spec
    states: each one the ledger lists as ungroundable, and each one the pass
    reports the site lacks that is no scope every search runs in."""
    held = {c.key for c in deps.state.domain.requirements}
    reported = {c.key for c in lacking}
    return [
        g.constraint
        for g in derive_ledger(deps.state, deps.intent).constraints.grounded
        if g.constraint.source is ConstraintSource.USER_EXPLICIT
        and g.constraint.key in held
        and (
            g.status is ConstraintStatus.UNGROUNDABLE
            or (
                g.constraint.kind not in STRATEGY_SCOPES
                and g.constraint.key in reported
            )
        )
    ]
