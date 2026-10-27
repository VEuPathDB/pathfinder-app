from __future__ import annotations

from pydantic_ai.tools import RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
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
