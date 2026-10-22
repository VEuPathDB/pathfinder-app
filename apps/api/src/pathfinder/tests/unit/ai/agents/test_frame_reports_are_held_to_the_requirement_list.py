"""FRAME reads the researcher's requirements as a numbered list, and a report
that names a number the list lacks is sent back to FRAME once, in its own run."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext

from pathfinder.ai.agents.frame_result_checks import (
    hold_the_reports_to_the_requirement_list,
)
from pathfinder.ai.agents.strategy_instructions import pinned_requirements
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        label=value,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _context() -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.agent_state.stated_requirements = [
        _stated(ConstraintKind.ORGANISM, "P. falciparum 3D7"),
        _stated(ConstraintKind.OTHER, "predicted GPI anchor"),
    ]
    return ctx


def _result(*numbers: str) -> FrameResult:
    return FrameResult(
        summary="No search on this site states a predicted GPI anchor.",
        requirement_problems=[
            RequirementReport(
                requirement=number, problem=RequirementProblem.SITE_HAS_NO_SEARCH
            )
            for number in numbers
        ],
    )


def test_frame_reads_the_requirements_under_their_numbers() -> None:
    assert pinned_requirements(_context()) == (
        "## Requirements the researcher stated\n"
        "- R1 (organism): P. falciparum 3D7\n"
        "- R2 (other): predicted GPI anchor"
    )


def test_a_report_of_a_listed_number_passes() -> None:
    result = _result("R2")

    assert hold_the_reports_to_the_requirement_list(_context(), result) is result


def test_a_number_the_list_lacks_is_sent_back_twice_with_the_numbers_it_holds() -> None:
    ctx = _context()
    result = _result("R2", "R5")

    with pytest.raises(ModelRetry) as sent_back:
        hold_the_reports_to_the_requirement_list(ctx, result)

    assert str(sent_back.value) == (
        "requirement_problems names ['R5'], and the list holds R1, R2. A report "
        "names a requirement by its number in 'Requirements the researcher "
        "stated'. Use one of those numbers, or leave the entry out and say it "
        "in summary."
    )
    with pytest.raises(ModelRetry):
        hold_the_reports_to_the_requirement_list(ctx, result)
    assert hold_the_reports_to_the_requirement_list(ctx, result) == _result(
        "R2"
    ).with_gap(
        "report_dropped",
        "The pass reported ['R5'], which the requirement list does not hold.",
    )
