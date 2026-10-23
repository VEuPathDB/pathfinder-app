from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext

from pathfinder.ai.agents.frame_choice_checks import hold_a_choice_to_its_readings
from pathfinder.ai.agents.frame_result_checks import (
    hold_the_reports_to_the_requirement_list,
)
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "phyletic_expression"
_PANEL = "c_panel"
_OPEN = RequirementProblem.REQUEST_LEAVES_IT_OPEN


def _slot(cid: str, param: str, **fields: object) -> OpenSlot:
    return OpenSlot.model_validate(
        {"criterionId": cid, "paramName": param, "question": "?"} | fields
    )


def _panel(**fields: object) -> Criterion:
    return Criterion.model_validate(
        {
            "id": _PANEL,
            "text": "present in the panel's genomes",
            "searchName": "GroupsByPhyleticPattern",
            "recordClass": "group",
            "openParams": [_slot(_PANEL, _EXPRESSION, paramKind="string")],
        }
        | fields
    )


def _context(*criteria: Criterion, refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=list(criteria)
    )
    ctx.deps.agent_state.refusals = refusals
    return ctx


def _question(**fields: object) -> SlotQuestion:
    return SlotQuestion.model_validate(
        {
            "question": "Which genomes should the panel hold?",
            "recommendedValue": "every genome",
            "criterionId": _PANEL,
            "paramName": _EXPRESSION,
        }
        | fields
    )


def _readings() -> list[Reading]:
    return [
        Reading(label="Every genome", value="AAAA=10T"),
        Reading(label="All but one genome", value="AAAA>=9T"),
    ]


def _asked(
    *questions: SlotQuestion, reports: list[RequirementReport] | None = None
) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=list(questions),
        requirement_problems=list(reports or []),
    )


def _report(key: str, problem: RequirementProblem) -> RequirementReport:
    return RequirementReport(requirement=key, problem=problem)


def _left_by_its_reason(term: str) -> Criterion:
    return _panel(
        rationale=SearchRationale(
            search_name="GroupsByPhyleticPattern",
            basis="parameter",
            term=term,
            reason="the expression decides it",
            tool_call_id="call_read",
        ),
        paramDisplayNames={_EXPRESSION: "Expression"},
    )


def test_a_slot_left_open_for_a_value_the_request_leaves_open_reaches_the_card() -> (
    None
):
    asked = _asked(
        _question(readings=_readings(), requirements=["R1"]),
        reports=[_report("R1", _OPEN)],
    )

    held = hold_a_choice_to_its_readings(
        _context(_left_by_its_reason("Expression")), asked
    )

    assert held == asked


@pytest.mark.parametrize(
    "reports",
    [[], [_report("R1", RequirementProblem.STAND_IN_BOUND)]],
)
def test_a_slot_left_open_for_a_stated_value_is_sent_back(
    reports: list[RequirementReport],
) -> None:
    asked = _asked(
        _question(readings=_readings(), requirements=["R1"]), reports=reports
    )

    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(
            _context(_left_by_its_reason("Expression")), asked
        )

    assert f"{_PANEL}.{_EXPRESSION} is left open" in str(sent_back.value)


def test_a_slot_left_open_for_a_stated_value_is_a_named_gap_at_the_bound() -> None:
    held = hold_a_choice_to_its_readings(
        _context(_left_by_its_reason(_EXPRESSION), refusals=REFUSALS_PER_CHECK),
        _asked(),
    )

    assert isinstance(held, FrameResult)
    assert held.gaps == [
        PassGap(
            kind="question_without_readings",
            sentence=(
                f"{_PANEL}.{_EXPRESSION} is left open with no requirement "
                "reported open for it."
            ),
        )
    ]


def test_a_stated_score_left_open_without_an_open_requirement_is_sent_back() -> None:
    score = Criterion(
        id="c_score",
        text="genes with an export score of at least 5",
        search_name="GenesByExportPrediction",
        open_params=[_slot("c_score", "min_score", paramKind="number")],
        param_display_names={"min_score": "Minimum Score"},
        rationale=SearchRationale(
            search_name="GenesByExportPrediction",
            basis="parameter",
            term="Minimum Score",
            reason="the score decides it",
            tool_call_id="call_read",
        ),
    )

    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(_context(score), _asked())

    assert "c_score.min_score is left open" in str(sent_back.value)


def test_a_slot_open_beside_a_reason_that_is_no_parameter_is_not_held() -> None:
    only_match = _panel(
        rationale=SearchRationale(
            search_name="GroupsByPhyleticPattern",
            basis="only_match",
            term="Expression",
            reason="no other search names it",
            tool_call_id="call_read",
        ),
        paramDisplayNames={_EXPRESSION: "Expression"},
    )

    assert hold_a_choice_to_its_readings(_context(only_match), _asked()) == _asked()


def test_an_unkeyed_question_on_an_open_slot_with_no_requirement_list_binds() -> None:
    ctx = _context(_left_by_its_reason("Expression"))
    ctx.deps.agent_state.stated_requirements = []
    asked = _asked(_question(readings=_readings()))

    listed = hold_the_reports_to_the_requirement_list(ctx, asked)
    held = hold_a_choice_to_its_readings(ctx, listed)

    assert held == asked
    assert isinstance(held, FrameResult)
    assert held.gaps == []
