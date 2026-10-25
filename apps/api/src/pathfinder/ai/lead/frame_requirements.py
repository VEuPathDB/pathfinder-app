"""The held requirements a framing pass reports the site has no search for or
failed to run, and the questions the card asks about them."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.expression_handles import held_readings
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    unanswered_questions,
    with_refusals,
    with_withdrawals,
)
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    refused_requirements,
    reported_requirements,
)
from pathfinder.domain.strategy.save_offers import with_save_offers


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


def _display_name(domain: StrategyDomainState, search: str) -> str:
    """The name the site shows for a search this turn read, else its own name."""
    read = domain.discovered_searches.get(search)
    return search if read is None else read.display_name


def questions_for_the_card(
    deps: LeadDeps, result: FrameResult, lacking: Sequence[Constraint]
) -> list[OpenQuestion]:
    """The pass's questions, with one per requirement whose search the site
    failed to run and a drop offer for each other one no search states, less
    those the researcher answered."""
    domain = deps.state.domain
    refused = [
        (requirement, _display_name(domain, search))
        for requirement, search in refused_requirements(
            result.requirement_problems, domain.requirements
        )
    ]
    kept = {requirement.key for requirement, _ in refused}
    unstated = [
        c for c in requirements_no_search_states(deps, lacking) if c.key not in kept
    ]
    return unanswered_questions(
        with_save_offers(
            with_refusals(
                with_withdrawals(
                    result.questions(
                        domain.operational_spec,
                        domain.requirements,
                        held_readings(domain.built_expressions),
                    ),
                    unstated,
                ),
                refused,
            ),
            domain.computed_comparisons,
        ),
        answered=[q.question for q in domain.answered_questions],
    )
