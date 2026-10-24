"""What a framing pass reports about a requirement the strategy does not answer
as asked. A report names the requirement by its number in the list the pass reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Literal

from assistant_core.platform.pydantic_base import computed
from pydantic import Field, TypeAdapter, model_validator
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)

RecordRole = Literal["answer", "through"]
_PATTERN: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)


class RecordTypeRole(CamelModel):
    requirement: str = Field(
        description=(
            "The number of a record-type requirement, such as R2, from "
            "'Requirements the researcher stated' in your instructions."
        )
    )
    role: RecordRole = Field(
        description=(
            "answer: the researcher wants these records as the result, so the "
            "root of the tree returns them. through: the tree passes through "
            "these records on the way to the result, as in groups that contain "
            "given proteins, so a step of the tree returns them."
        )
    )


def record_roles(
    stated: Sequence[RecordTypeRole], requirements: Sequence[Constraint]
) -> dict[str, RecordRole]:
    numbered = numbered_requirements(requirements)
    return {
        held.key: role.role
        for role in stated
        if (held := numbered.get(role.requirement)) is not None
        and held.kind is ConstraintKind.RECORD_TYPE
    }


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
    clause: str = Field(
        default="",
        description=(
            "Only for a requirement about which genomes hold a group's proteins, "
            "such as an absence or a share of a set's genomes: the requirement as "
            "one pattern term in build_phyletic_expression's form, written as "
            "JSON. A requirement a term of the bound expression states is met and "
            "is never reported. Empty for any other requirement."
        ),
    )

    def clause_pattern(self) -> PhyleticPattern | None:
        """The clause as a pattern term; raises when it is none."""
        return _PATTERN.validate_json(self.clause) if self.clause.strip() else None

    @model_validator(mode="after")
    def _a_search_and_a_site_only_where_the_problem_takes_them(
        self,
    ) -> RequirementReport:
        if self.problem is not RequirementProblem.SITE_REFUSED_THE_SEARCH:
            self.search = ""
        if self.problem is not RequirementProblem.ANOTHER_SITE_ANSWERS:
            self.site = ""
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
    """Each requirement the researcher stated, then each record type the thread
    assumed, under the number a pass reads."""
    stated = [c for c in requirements if c.source is ConstraintSource.USER_EXPLICIT]
    assumed = [
        c
        for c in requirements
        if c.source is not ConstraintSource.USER_EXPLICIT
        and c.kind is ConstraintKind.RECORD_TYPE
    ]
    return {f"R{number}": c for number, c in enumerate([*stated, *assumed], start=1)}


def stated_numbers(requirements: Sequence[Constraint]) -> list[str]:
    return [
        number
        for number, c in numbered_requirements(requirements).items()
        if c.source is ConstraintSource.USER_EXPLICIT
    ]


def _kind_of(c: Constraint) -> str:
    if c.source is ConstraintSource.USER_EXPLICIT:
        return c.kind.value
    return f"{c.kind.value}, assumed"


def requirements_block(requirements: Sequence[Constraint]) -> str | None:
    """The numbered list a pass reads, or None when it numbers nothing."""
    numbered = numbered_requirements(requirements)
    if not numbered:
        return None
    lines = [
        f"- {number} ({_kind_of(c)}): {c.requested_value}"
        for number, c in numbered.items()
    ]
    return "\n".join(["## Requirements the researcher stated", *lines])


def record_types_without_a_role(
    stated: Sequence[RecordTypeRole],
    requirements: Sequence[Constraint],
    held: Mapping[str, RecordRole],
) -> dict[str, Constraint]:
    roled = {role.requirement for role in stated}
    return {
        number: c
        for number, c in numbered_requirements(requirements).items()
        if c.kind is ConstraintKind.RECORD_TYPE
        and number not in roled
        and c.key not in held
    }


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
