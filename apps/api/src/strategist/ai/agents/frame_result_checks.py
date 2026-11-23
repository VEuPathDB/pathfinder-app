"""What FRAME's result is held to inside its own run, before the dispatch reads it."""

from __future__ import annotations

from pydantic_ai import RunContext
from veupathdb.wdk import get_site_router

from strategist.ai.agents.held_answer import (
    Changed,
    Gaps,
    HeldAnswer,
    asked_gaps,
    gapped,
    held,
)
from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.deltas import FrameResult, PassGap, PassGapKind
from strategist.ai.lead.frame_questions import questions_that_bind_to_nothing
from strategist.domain.refusal import Check, RefusalKey
from strategist.domain.strategy.constraints import CONSTRAINT_KINDS
from strategist.domain.strategy.organism_steps import organisms_no_step_limits
from strategist.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
    numbered_requirements,
    unknown_requirement_ids,
)
from strategist.domain.strategy.structure_bindings import unbound_in_structure
from strategist.services.gene_sets.homes import site_kind


def _dropped(report: RequirementReport) -> Changed:
    def let_through(output: FrameResult) -> FrameResult:
        kept_reports = [r for r in output.requirement_problems if r != report]
        return output.model_copy(update={"requirement_problems": kept_reports})

    return let_through


def _dropped_with_gap(
    report: RequirementReport, kind: PassGapKind, sentence: str
) -> tuple[Gaps, Changed]:
    return gapped(PassGap(kind=kind, sentence=sentence)), _dropped(report)


def hold_the_reports_to_the_requirement_list(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    held_list = ctx.deps.agent_state.stated_requirements
    unknown = unknown_requirement_ids(output.requirement_problems, held_list)
    holds = ", ".join(numbered_requirements(held_list)) or "none"
    return [
        held(
            RefusalKey(
                check=Check.THE_REPORTS_TO_THE_REQUIREMENT_LIST, criterion=number
            ),
            (
                f"requirement_problems names {number}, and the list holds {holds}. "
                "A report names a requirement by its number in 'Requirements the "
                "researcher stated'. Use one of those numbers, or leave the entry "
                "out and say it in summary."
            ),
            *_dropped_with_gap(
                report,
                "report_dropped",
                f"The pass reported {number}, which the requirement list does not "
                "hold.",
            ),
        )
        for report in output.requirement_problems
        if (number := report.requirement) in unknown
    ]


def hold_an_organism_to_a_step(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    if output.disposition != "spec_ready":
        return []
    state = ctx.deps.agent_state
    unmet = organisms_no_step_limits(
        state.stated_requirements,
        output.requirement_problems,
        state.operational_spec_draft,
    )
    numbered = numbered_requirements(state.stated_requirements)
    remedy = (
        "Add a step that does, such as the sequence search by taxonomy "
        "(ByTaxonomy) intersected with the proteins, or a search whose organism "
        "parameter names it."
        if site_kind(ctx.deps.site_id) == "orthomcl"
        else "Bind the organism parameter of a search that has one to it."
    )
    asked = [(number, numbered[number].requested_value) for number in unmet]
    return [
        held(
            RefusalKey(check=Check.AN_ORGANISM_TO_A_STEP, criterion=number),
            (
                f"{number} asks for {value} (organism), and no step of the draft "
                "limits its records to an organism. A unit of a phyletic "
                f"expression or the text of a transform does not. {remedy} If no "
                f"search can, report {number} in requirement_problems."
            ),
            gapped(
                PassGap(
                    kind="organism_step_missing",
                    sentence=(
                        "No step limits the records to the organism "
                        f"{number} asks for: {value}."
                    ),
                )
            ),
        )
        for number, value in asked
    ]


def hold_the_structure_to_bound_criteria(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    if output.disposition != "spec_ready":
        return []
    return [
        held(
            RefusalKey(check=Check.THE_STRUCTURE_TO_BOUND_CRITERIA, criterion=node),
            (
                f"set_structure names {node}, and the draft binds no search for "
                "it. Bind it with set_criterion, or call set_structure again "
                "without it: the build refuses a node no bound criterion stands "
                "for."
            ),
            gapped(
                PassGap(
                    kind="structure_names_unbound",
                    sentence=(
                        f"The structure names {node}, which no bound criterion "
                        "stands for."
                    ),
                )
            ),
        )
        for node in unbound_in_structure(ctx.deps.agent_state.operational_spec_draft)
    ]


def hold_the_questions_to_the_draft(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    if output.disposition != "needs_user":
        return []
    state = ctx.deps.agent_state
    unbound = questions_that_bind_to_nothing(
        output, state.operational_spec_draft, state.sets_the_site
    )
    if not unbound:
        return []
    gap = PassGap(
        kind="questions_bind_nothing",
        sentence="The pass asks questions whose answers bind nothing its draft holds.",
    )

    def gaps(final: FrameResult) -> list[PassGap]:
        still = questions_that_bind_to_nothing(
            final, state.operational_spec_draft, state.sets_the_site
        )
        return [gap] if still else []

    return [held(RefusalKey(check=Check.THE_QUESTIONS_TO_THE_DRAFT), unbound, gaps)]


def hold_the_questions_to_a_dimension(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    del ctx
    undecided = set(output.undecided_questions)
    return [
        held(
            RefusalKey(
                check=Check.THE_QUESTIONS_TO_A_DIMENSION,
                criterion=question.criterion_id,
                parameter=question.param_name,
            ),
            (
                f"The open question {question.question!r} decides nothing. Give it "
                "the `dimension` its open parameter states, one of "
                f"{CONSTRAINT_KINDS}, and the `recommended_value` you would use if "
                "the user does not answer."
            ),
            asked_gaps(
                question,
                PassGap(
                    kind="question_decides_nothing",
                    sentence=(
                        f"The question {question.question!r} names no dimension and "
                        "recommends no value."
                    ),
                ),
            ),
        )
        for question in output.open_questions
        if question.question in undecided
    ]


def hold_the_route_to_another_site(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    others = sorted(
        site.id
        for site in get_site_router().list_sites()
        if site.id != ctx.deps.site_id
    )
    return [
        held(
            RefusalKey(
                check=Check.THE_ROUTE_TO_ANOTHER_SITE, criterion=report.requirement
            ),
            (
                f"another_site_answers for {report.requirement} names "
                f"{report.site!r}, which is no other site. Name one of "
                f"{', '.join(others)}, or bind the search this site holds."
            ),
            *_dropped_with_gap(
                report,
                "report_dropped",
                f"The pass named {report.site!r} as another site that answers "
                f"{report.requirement}, and it is none.",
            ),
        )
        for report in output.requirement_problems
        if report.problem is RequirementProblem.ANOTHER_SITE_ANSWERS
        and report.site not in others
    ]


def _misreport(report: RequirementReport, state: AgentToolState) -> str | None:
    refused = state.refused_searches
    if (
        report.problem is not RequirementProblem.SITE_REFUSED_THE_SEARCH
        or report.search in refused
    ):
        return None
    named = f"site_refused_the_search for {report.requirement}"
    if not report.search:
        return (
            f"{named} names no search: put the search the site refused in "
            "`search`, or report the requirement as site_has_no_search."
        )
    if report.search in state.builder_refusals:
        return (
            f"{named} names {report.search}, and the site never ran it: "
            "build_phyletic_expression's own limit refused the pattern "
            f"({state.builder_refusals[report.search]}). Narrow the pattern, or "
            "report the requirement as site_has_no_search."
        )
    if report.search in state.unserved_searches:
        return (
            f"{named} names {report.search}, which the site's catalog lists under "
            "no record type. A requirement no search on this site answers is "
            "site_has_no_search."
        )
    if refused:
        return (
            f"{named} names {report.search}, and this turn saw the site refuse "
            f"only {', '.join(refused)}. Name one of those, or report the "
            "requirement as site_has_no_search."
        )
    return (
        f"{named} names {report.search}, and the site refused no search this "
        "turn. A requirement no search on this site answers is site_has_no_search."
    )


def _missing_after_refusal(
    output: FrameResult, refused: dict[str, str]
) -> list[HeldAnswer]:
    missing = any(
        r.problem is RequirementProblem.SITE_HAS_NO_SEARCH
        for r in output.requirement_problems
    )
    if not refused or not missing:
        return []
    answers = "; ".join(f"{name} ({answer})" for name, answer in refused.items())
    gap = PassGap(
        kind="missing_after_refusal",
        sentence=(
            "The pass reports a requirement no search answers after the site "
            f"refused {', '.join(refused)} this turn."
        ),
    )
    said = (
        f"The site refused to run {answers} this turn. A requirement that search "
        "answers is site_refused_the_search with that search named in search, not "
        "site_has_no_search. Keep site_has_no_search for a requirement no search "
        "on this site answers."
    )
    return [
        held(RefusalKey(check=Check.THE_REPORTS_TO_THE_REFUSALS), said, gapped(gap))
    ]


def hold_the_reports_to_the_refusals(
    ctx: RunContext[AgentDeps], output: FrameResult
) -> list[HeldAnswer]:
    state = ctx.deps.agent_state
    misreported = [
        held(
            RefusalKey(
                check=Check.THE_REPORTS_TO_THE_REFUSALS, criterion=r.requirement
            ),
            said,
            *_dropped_with_gap(
                r,
                "report_dropped",
                f"The pass reported the site refused {r.search!r} for "
                f"{r.requirement}, and it did not this turn.",
            ),
        )
        for r in output.requirement_problems
        if (said := _misreport(r, state)) is not None
    ]
    return [*misreported, *_missing_after_refusal(output, state.refused_searches)]


__all__ = [
    "hold_an_organism_to_a_step",
    "hold_the_questions_to_a_dimension",
    "hold_the_questions_to_the_draft",
    "hold_the_reports_to_the_refusals",
    "hold_the_reports_to_the_requirement_list",
    "hold_the_route_to_another_site",
    "hold_the_structure_to_bound_criteria",
]
