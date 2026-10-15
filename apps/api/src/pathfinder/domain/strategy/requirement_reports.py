"""What a framing pass reports about a requirement the strategy does not answer
as asked. A report names the requirement by its number in the list the pass reads."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from assistant_core.platform.pydantic_base import computed
from pydantic import Field, model_validator
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import Constraint, ConstraintSource


class RequirementProblem(StrEnum):
    SITE_HAS_NO_SEARCH = "site_has_no_search"
    STAND_IN_BOUND = "stand_in_bound"
    NEEDS_THE_ANALYSIS_WORKFLOW = "needs_the_analysis_workflow"
    REQUEST_LEAVES_IT_OPEN = "request_leaves_it_open"
    ANOTHER_SITE_ANSWERS = "another_site_answers"
    SITE_REFUSED_THE_SEARCH = "site_refused_the_search"


class RequirementReport(CamelModel):
    requirement: str = Field(
        description=(
            "The number of the requirement, such as R2, from 'Requirements the "
            "researcher stated' in your instructions."
        )
    )
    problem: RequirementProblem = Field(
        description=(
            "site_has_no_search: no search on this site can answer it, and "
            "nothing is bound for it. stand_in_bound: you bound the nearest "
            "search in its place, and it is not what was asked. "
            "needs_the_analysis_workflow: it changes or needs a study analysis "
            "that only the Lead's analysis tools write. request_leaves_it_open: "
            "the request does not give a value a parameter needs, and you ask "
            "for it in open_questions. another_site_answers: no search on this "
            "site can state it, a search on the site you name in `site` can, "
            "and nothing is bound for it. site_refused_the_search: a search on "
            "this site answers it, the site refused to run that search, which "
            "you name in `search`, and nothing is bound for it."
        )
    )
    site: str = Field(
        default="",
        description=(
            "Only for another_site_answers: the id of the site whose search "
            "answers it, such as orthomcl."
        ),
    )

    search: str = Field(
        default="",
        description=(
            "Only for site_refused_the_search: the name of the search the site "
            "refused to run, such as MapProteinsByDiamond."
        ),
    )

    @model_validator(mode="after")
    def _a_search_only_for_a_refusal(self) -> RequirementReport:
        names_a_search = self.problem is RequirementProblem.SITE_REFUSED_THE_SEARCH
        if names_a_search != bool(self.search):
            msg = (
                "search names the search the site refused to run, so it is set "
                "for site_refused_the_search and for no other problem"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _a_site_only_for_another_site(self) -> RequirementReport:
        names_a_site = self.problem is RequirementProblem.ANOTHER_SITE_ANSWERS
        if names_a_site != bool(self.site):
            msg = (
                "site names the site whose search answers the requirement, so it "
                "is set for another_site_answers and for no other problem"
            )
            raise ValueError(msg)
        return self


_WHAT_THE_LEAD_DOES = {
    RequirementProblem.SITE_HAS_NO_SEARCH: (
        "The site has no search for it. The card asks whether to drop it; say "
        "what the site lacks."
    ),
    RequirementProblem.STAND_IN_BOUND: (
        "A nearby search stands in its place. Name the stand-in and say it is "
        "not what was asked."
    ),
    RequirementProblem.NEEDS_THE_ANALYSIS_WORKFLOW: (
        "A framing pass cannot write an analysis. Do it with your analysis tools."
    ),
    RequirementProblem.REQUEST_LEAVES_IT_OPEN: (
        "The request gives no value for it. The card asks for the value."
    ),
    RequirementProblem.ANOTHER_SITE_ANSWERS: (
        "Another site answers it. FRAME's summary carries the sentence that opens "
        "a conversation there; give it word for word and ask nothing about it."
    ),
    RequirementProblem.SITE_REFUSED_THE_SEARCH: (
        "The site has a search for it and failed to run it. The card asks whether "
        "to keep it for a later try; say the site failed, never that it lacks the search."
    ),
}


class ReportedRequirement(CamelModel):
    """A report as the Lead reads it: the requirement in the words the thread holds."""

    requirement: str
    problem: RequirementProblem

    @computed
    def what_to_do(self) -> str:
        """What the Lead does about this problem."""
        return _WHAT_THE_LEAD_DOES[self.problem]


def numbered_requirements(requirements: Sequence[Constraint]) -> dict[str, Constraint]:
    """Each requirement the researcher stated, under the number a pass reads."""
    stated = [c for c in requirements if c.source is ConstraintSource.USER_EXPLICIT]
    return {f"R{number}": c for number, c in enumerate(stated, start=1)}


def requirements_block(requirements: Sequence[Constraint]) -> str | None:
    """The numbered list a pass reads, or None when the researcher stated nothing."""
    numbered = numbered_requirements(requirements)
    if not numbered:
        return None
    lines = [f"- {number}: {c.requested_value}" for number, c in numbered.items()]
    return "\n".join(["## Requirements the researcher stated", *lines])


def reported_requirements(
    reports: Sequence[RequirementReport],
    requirements: Sequence[Constraint],
    problem: RequirementProblem,
) -> list[Constraint]:
    """The held requirements the reports name with this problem."""
    numbered = numbered_requirements(requirements)
    return [
        numbered[report.requirement]
        for report in reports
        if report.problem is problem and report.requirement in numbered
    ]


def refused_requirements(
    reports: Sequence[RequirementReport], requirements: Sequence[Constraint]
) -> list[tuple[Constraint, str]]:
    """Each held requirement a report says the site refused to run a search for,
    with that search."""
    numbered = numbered_requirements(requirements)
    return [
        (numbered[report.requirement], report.search)
        for report in reports
        if report.problem is RequirementProblem.SITE_REFUSED_THE_SEARCH
        and report.requirement in numbered
    ]


def unknown_requirement_ids(
    reports: Sequence[RequirementReport], requirements: Sequence[Constraint]
) -> list[str]:
    """The numbers the reports name that the list does not hold."""
    numbered = numbered_requirements(requirements)
    return [r.requirement for r in reports if r.requirement not in numbered]


def resolved_reports(
    reports: Sequence[RequirementReport], requirements: Sequence[Constraint]
) -> list[ReportedRequirement]:
    """Each report whose number the list holds, with the held words in its place."""
    numbered = numbered_requirements(requirements)
    return [
        ReportedRequirement(
            requirement=numbered[report.requirement].requested_value,
            problem=report.problem,
        )
        for report in reports
        if report.requirement in numbered
    ]
