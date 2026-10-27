from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
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
from pathfinder.services.strategies import reading_check
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "phyletic_expression"
_PANEL = "c_panel"
_ALL, _MOST = "AAAA=10T", "AAAA>=9T"
_PICK = "c_pick"
_ORGANISM = "organism"
_STATED = [
    Constraint(
        kind=ConstraintKind.OTHER,
        label=label,
        requested_value=label,
        source=ConstraintSource.USER_EXPLICIT,
    )
    for label in ("the panel of genomes", "a missing marker")
]


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


def _picked(*slots: OpenSlot) -> Criterion:
    return Criterion(
        id=_PICK,
        text="records picked",
        search_name="AnySearch",
        open_params=list(slots),
    )


def _context(*criteria: Criterion, refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    state = ctx.deps.agent_state
    state.operational_spec_draft = OperationalSpec(criteria=list(criteria))
    state.stated_requirements = list(_STATED)
    state.refusals = refusals
    return ctx


def _question(**fields: object) -> SlotQuestion:
    return SlotQuestion.model_validate(
        {
            "question": "Which genomes should the panel hold?",
            "dimension": ConstraintKind.ORGANISM,
            "recommendedValue": "every genome",
            "criterionId": _PANEL,
            "paramName": _EXPRESSION,
        }
        | fields
    )


def _readings() -> list[Reading]:
    return [
        Reading(label="Every genome", value=_ALL),
        Reading(label="All but one genome", value=_MOST),
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


_OPEN = RequirementProblem.REQUEST_LEAVES_IT_OPEN


_H11_STATED = [
    Constraint(
        kind=ConstraintKind.ORGANISM,
        label="trypanosomatid organisms",
        requested_value="trypanosomatid",
        source=ConstraintSource.USER_EXPLICIT,
    ),
    Constraint(
        kind=ConstraintKind.OTHER,
        label="absence of a human counterpart",
        requested_value="gene families with no human counterpart",
        source=ConstraintSource.USER_EXPLICIT,
    ),
]
_H11_FRAME = {
    "disposition": "needs_user",
    "summary": "No clade code names the group.",
    "openQuestions": [
        {
            "question": (
                "Which trypanosomatid genomes or species should define the family "
                "set? The search can then require presence in that selected list "
                "and absence from human."
            ),
            "dimension": "organism",
            "recommendedValue": "Specify the trypanosomatid species/genomes to include",
            "options": [
                "Trypanosoma brucei",
                "Trypanosoma cruzi",
                "Trypanosoma vivax",
                "Leishmania species",
                "A custom list of trypanosomatid genomes",
            ],
        }
    ],
    "requirementProblems": [{"requirement": "R1", "problem": "site_has_no_search"}],
}


@pytest.fixture
def echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


def _pick_question(param: str, **fields: object) -> SlotQuestion:
    return _question(criterionId=_PICK, paramName=param, **fields)
