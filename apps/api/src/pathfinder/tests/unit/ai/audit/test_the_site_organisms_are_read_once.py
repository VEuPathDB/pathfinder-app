from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic_ai import AgentRunResult, DeferredToolRequests
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb.errors import WDKError

from pathfinder.ai.audit import run_tools
from pathfinder.ai.audit.auditor import build_auditor_agent
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.reply import AuditReply
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.services.audit import planning
from pathfinder.services.audit.views import AuditRunSummary
from pathfinder.tests._support.audit_planning import ORGANISMS
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_part,
    lead_deps,
    pipeline_state,
    user_intent,
)

_PLAN = "plan_gene_model_audit"
_LIST = "list_audit_runs"
_HELD = {"type": "string", "enum": ORGANISMS}
_PLAIN = {"type": "string"}


class Organisms:
    def __init__(self, failure: Exception | None) -> None:
        self.failure = failure
        self.reads = 0

    async def list_organisms(self, site_id: str) -> list[str]:
        del site_id
        self.reads += 1
        if self.failure is not None:
            raise self.failure
        return list(ORGANISMS)


class Steps:
    def __init__(self, answer: Callable[[AgentInfo], ToolCallPart]) -> None:
        self.answer = answer
        self.genomes: list[dict[str, Any]] = []

    def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        (plan,) = [t for t in info.function_tools if t.name == _PLAN]
        self.genomes.append(plan.parameters_json_schema["properties"]["genomes"])
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name=_LIST, args={})])
        return ModelResponse(parts=[self.answer(info)])


def _read_by(monkeypatch: pytest.MonkeyPatch, failure: Exception | None) -> Organisms:
    organisms = Organisms(failure)
    monkeypatch.setattr(planning, "list_organisms", organisms.list_organisms)

    async def no_runs(user_id: UUID) -> list[AuditRunSummary]:
        del user_id
        return []

    monkeypatch.setattr(run_tools, "list_runs", no_runs)
    return organisms


_FAILURES = [
    httpx.ReadTimeout("GenesByTaxon search details timed out"),
    WDKError("search details timed out", status=504),
]


async def _lead_turn(steps: Steps) -> None:
    state = pipeline_state(user_prompt="show my audit runs")
    state.turn_markers.intent_classified = True
    deps = lead_deps(state, intent=user_intent(IntentClassification.GENE_MODEL_AUDIT))
    await build_lead_agent().run("q", deps=deps, model=FunctionModel(steps.respond))


async def _auditor_turn(steps: Steps) -> AuditReply | DeferredToolRequests:
    deps = AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())
    result: AgentRunResult[AuditReply | DeferredToolRequests]
    result = await build_auditor_agent().run(
        "show my audit runs",
        deps=deps,
        model=FunctionModel(steps.respond),
        output_type=[AuditReply, DeferredToolRequests],
    )
    return result.output


def _lead_answer(info: AgentInfo) -> ToolCallPart:
    del info
    return final_result_part(
        {
            "prose": "No audit run is stored.",
            "nextState": "await_user",
            "strategyChanged": False,
        }
    )


def _auditor_answer(info: AgentInfo) -> ToolCallPart:
    (tool,) = info.output_tools
    return ToolCallPart(tool_name=tool.name, args={"prose": "No audit run is stored."})


@pytest.mark.parametrize("failure", _FAILURES)
async def test_a_failed_read_leaves_the_leads_audit_reads_working(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    organisms = _read_by(monkeypatch, failure)
    steps = Steps(_lead_answer)

    await _lead_turn(steps)

    assert organisms.reads == 1
    assert [g["items"] for g in steps.genomes] == [_PLAIN, _PLAIN]


@pytest.mark.parametrize("failure", _FAILURES)
async def test_a_failed_read_leaves_the_auditors_reads_working(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    organisms = _read_by(monkeypatch, failure)
    steps = Steps(_auditor_answer)

    output = await _auditor_turn(steps)

    assert output == AuditReply(prose="No audit run is stored.")
    assert organisms.reads == 1
    assert [g["items"] for g in steps.genomes] == [_PLAIN, _PLAIN]


async def test_two_lead_steps_read_the_organisms_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organisms = _read_by(monkeypatch, None)
    steps = Steps(_lead_answer)

    await _lead_turn(steps)

    assert organisms.reads == 1
    assert [g["items"] for g in steps.genomes] == [_HELD, _HELD]


async def test_two_auditor_steps_read_the_organisms_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organisms = _read_by(monkeypatch, None)
    steps = Steps(_auditor_answer)

    await _auditor_turn(steps)

    assert organisms.reads == 1
    assert [g["items"] for g in steps.genomes] == [_HELD, _HELD]
