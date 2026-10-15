"""A framing pass reports a requirement by its number in the list it was shown,
so the words of a report are the words the thread holds."""

from __future__ import annotations

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.requirement_reports import (
    ReportedRequirement,
    RequirementProblem,
    RequirementReport,
    numbered_requirements,
    reported_requirements,
    requirements_block,
    resolved_reports,
    unknown_requirement_ids,
)


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        label=value,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_ORGANISM = _stated(ConstraintKind.ORGANISM, "P. falciparum 3D7")
_GPI = _stated(ConstraintKind.OTHER, "predicted GPI anchor")
_ASSUMED = Constraint(
    kind=ConstraintKind.COMBINATION,
    label="combination",
    requested_value="signal peptide AND GPI anchor",
)
_HELD = [_ORGANISM, _ASSUMED, _GPI]


def _report(requirement: str, problem: RequirementProblem) -> RequirementReport:
    return RequirementReport(requirement=requirement, problem=problem)


def test_only_what_the_researcher_stated_is_numbered_in_the_order_held() -> None:
    assert numbered_requirements(_HELD) == {"R1": _ORGANISM, "R2": _GPI}


def test_the_block_prints_each_number_beside_the_held_words() -> None:
    assert requirements_block(_HELD) == (
        "## Requirements the researcher stated\n"
        "- R1: P. falciparum 3D7\n"
        "- R2: predicted GPI anchor"
    )


def test_no_stated_requirement_numbers_nothing_and_prints_no_block() -> None:
    assert (numbered_requirements([_ASSUMED]), requirements_block([_ASSUMED])) == (
        {},
        None,
    )


def test_a_report_resolves_to_the_requirement_its_number_names() -> None:
    reports = [
        _report("R2", RequirementProblem.SITE_HAS_NO_SEARCH),
        _report("R1", RequirementProblem.STAND_IN_BOUND),
    ]

    assert reported_requirements(
        reports, _HELD, RequirementProblem.SITE_HAS_NO_SEARCH
    ) == [_GPI]
    assert reported_requirements(reports, _HELD, RequirementProblem.STAND_IN_BOUND) == [
        _ORGANISM
    ]


def test_a_number_the_list_lacks_resolves_to_nothing_and_is_named() -> None:
    reports = [
        _report("R7", RequirementProblem.SITE_HAS_NO_SEARCH),
        _report("R2", RequirementProblem.SITE_HAS_NO_SEARCH),
    ]

    assert reported_requirements(
        reports, _HELD, RequirementProblem.SITE_HAS_NO_SEARCH
    ) == [_GPI]
    assert unknown_requirement_ids(reports, _HELD) == ["R7"]


def test_the_lead_reads_each_report_in_the_held_words() -> None:
    reports = [
        _report("R2", RequirementProblem.NEEDS_THE_ANALYSIS_WORKFLOW),
        _report("R9", RequirementProblem.STAND_IN_BOUND),
    ]

    assert resolved_reports(reports, _HELD) == [
        ReportedRequirement(
            requirement="predicted GPI anchor",
            problem=RequirementProblem.NEEDS_THE_ANALYSIS_WORKFLOW,
        )
    ]


def test_each_report_tells_the_lead_what_to_do() -> None:
    told = {
        problem: ReportedRequirement(requirement="x", problem=problem).what_to_do
        for problem in RequirementProblem
    }

    assert told == {
        RequirementProblem.SITE_HAS_NO_SEARCH: (
            "The site has no search for it. The card asks whether to drop it; "
            "say what the site lacks."
        ),
        RequirementProblem.STAND_IN_BOUND: (
            "A nearby search stands in its place. Name the stand-in and say it "
            "is not what was asked."
        ),
        RequirementProblem.NEEDS_THE_ANALYSIS_WORKFLOW: (
            "A framing pass cannot write an analysis. Do it with your analysis tools."
        ),
        RequirementProblem.REQUEST_LEAVES_IT_OPEN: (
            "The request gives no value for it. The card asks for the value."
        ),
        RequirementProblem.ANOTHER_SITE_ANSWERS: (
            "Another site answers it. FRAME's summary carries the sentence that "
            "opens a conversation there; give it word for word and ask nothing "
            "about it."
        ),
        RequirementProblem.SITE_REFUSED_THE_SEARCH: (
            "The site has a search for it and failed to run it. The card asks "
            "whether to keep it for a later try; say the site failed, never that "
            "it lacks the search."
        ),
    }
