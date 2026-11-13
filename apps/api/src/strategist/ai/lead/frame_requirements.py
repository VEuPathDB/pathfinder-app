"""The held requirements a framing pass reports the site has no search for or
failed to run, and the questions the card asks about them and about each
combine the researcher's words read as another operator."""

from __future__ import annotations

from collections.abc import Sequence

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.derive import derive_ledger
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone.graph_helpers import counted_noun
from strategist.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintSource,
    ConstraintStatus,
)
from strategist.domain.strategy.expression_handles import held_readings
from strategist.domain.strategy.linked_values import linked_by_none
from strategist.domain.strategy.operator_questions import operator_questions
from strategist.domain.strategy.organism_picks import organism_questions
from strategist.domain.strategy.questions import (
    OpenQuestion,
    unanswered_questions,
    with_refusals,
    with_withdrawals,
)
from strategist.domain.strategy.requirement_reports import (
    RequirementProblem,
    refused_requirements,
    reported_requirements,
)
from strategist.domain.strategy.save_offers import with_save_offers


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
    states: each one the ledger lists as ungroundable, each value no criterion
    links once a search is bound, and each one the pass reports the site lacks
    that is no scope every search runs in."""
    held = {c.id for c in deps.state.domain.requirements}
    reported = {c.id for c in lacking}
    spec = deps.state.domain.operational_spec
    criteria = [] if spec is None else spec.criteria
    return [
        g.constraint
        for g in derive_ledger(deps.state, deps.intent).constraints.grounded
        if g.constraint.source is ConstraintSource.USER_EXPLICIT
        and g.constraint.id in held
        and (
            g.status is ConstraintStatus.UNGROUNDABLE
            or (
                g.status is not ConstraintStatus.PROVISIONAL
                and linked_by_none(g.constraint, criteria)
            )
            or (
                g.constraint.kind not in STRATEGY_SCOPES and g.constraint.id in reported
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
    failed to run, a drop offer for each other one no search states, one per
    combine the researcher's words read as another operator and one per organism
    requirement no site entry settles, less those the researcher answered."""
    domain = deps.state.domain
    refused = [
        (requirement, _display_name(domain, search))
        for requirement, search in refused_requirements(
            result.requirement_problems, domain.requirements
        )
    ]
    kept = {requirement.id for requirement, _ in refused}
    spec = domain.operational_spec
    criteria = [] if spec is None else spec.criteria
    unstated = [
        c for c in requirements_no_search_states(deps, lacking) if c.id not in kept
    ]
    operators = (
        []
        if spec is None
        else operator_questions(
            spec, domain.requirements, noun=counted_noun(spec.record_type)
        )
    )
    return unanswered_questions(
        [
            *with_save_offers(
                with_refusals(
                    with_withdrawals(
                        result.questions(
                            domain.operational_spec,
                            domain.requirements,
                            held_readings(domain.built_expressions),
                        ),
                        unstated,
                        criteria=criteria,
                    ),
                    refused,
                ),
                domain.computed_comparisons,
            ),
            *operators,
            *organism_questions(domain.requirements, domain.organism_picks),
        ],
        answered=[q.question for q in domain.answered_questions],
    )
