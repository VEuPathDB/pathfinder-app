"""The turn records every control test it ran, as the test filed its controls."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import (
    DurableCall,
    DurableTaskResult,
    PendingDurableCall,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import experiment
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.experiment.published_names import PublishedNames
from pathfinder.services.parameter_optimization.config import (
    SweepResult,
    SweepVariantResult,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_TASK_ID = UUID("0c6100d2-0000-4000-8000-000000000002")
_STEP_ID = 440299573
_HISTORY = ModelMessagesTypeAdapter.dump_json(
    [ModelRequest(parts=[UserPromptPart(content="test my controls")])],
).decode()
_RECOVERED = ["PF3D7_1031000", "PF3D7_1222600"]
_MISSED = ["PF3D7_0000001"]
_EXCLUDED = ["PF3D7_0102600", "PF3D7_0213400"]


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _deps() -> LeadDeps:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="test my controls",
        user_message_id=uuid4(),
    )
    state.pending_durable_call = PendingDurableCall(
        phase="lead",
        tool_call_id="call_controls",
        tool_name="run_control_tests_on_step",
        tool_args={"wdk_step_id": _STEP_ID},
        prior_messages_json=_HISTORY,
        durable_calls=[
            DurableCall(
                tool_call_id="call_controls",
                tool_name="run_control_tests_on_step",
                args={"wdk_step_id": _STEP_ID},
                task_id=_TASK_ID,
                durable_tool_name="run_control_tests_on_step",
            ),
        ],
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_quota_offline,
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=context, retrieved_memories=[])


def _worker_answer() -> dict[str, Any]:
    """The dict the control-test worker answers with."""
    outcome = ControlOutcome(
        step_id=_STEP_ID,
        search_name="GenesByMolecularWeight",
        estimated_size=132,
        positive_recovered_ids=_RECOVERED,
        positive_missed_ids=_MISSED,
        negative_admitted_ids=[],
        negative_excluded_ids=_EXCLUDED,
    )
    answer = outcome.model_dump(by_alias=True, exclude_none=True, mode="json")
    answer["targetLabel"] = "Genes by Molecular Weight"
    return answer


def _expected(wdk_step_id: int | None) -> ControlTestEvidence:
    return ControlTestEvidence(
        tested_label="Genes by Molecular Weight",
        wdk_step_id=wdk_step_id,
        positive=ControlSetEvidence(returned=_RECOVERED, not_returned=_MISSED),
        negative=ControlSetEvidence(returned=[], not_returned=_EXCLUDED),
    )


async def test_a_durable_control_test_is_recorded_as_the_worker_filed_it() -> None:
    deps = _deps()
    deps.state.durable_result = DurableTaskResult(
        task_id=_TASK_ID, status="success", result=_worker_answer()
    )

    await resolve_turn_resumption(state=deps.state, deps=deps)

    runs = deps.state.turn_markers.control_tests
    assert [run.tool_call_id for run in runs] == ["call_controls"]
    assert runs[0].evidence == _expected(_STEP_ID)


async def test_a_sweep_records_each_setting_it_scored() -> None:
    deps = _deps()
    deps.state.pending_durable_call = PendingDurableCall(
        phase="lead",
        tool_call_id="call_sweep",
        tool_name="optimize_search_parameters",
        tool_args={"wdk_step_id": _STEP_ID},
        prior_messages_json=_HISTORY,
        durable_calls=[
            DurableCall(
                tool_call_id="call_sweep",
                tool_name="optimize_search_parameters",
                args={"wdk_step_id": _STEP_ID},
                task_id=_TASK_ID,
                durable_tool_name="optimize_search_parameters",
            ),
        ],
    )
    sweep = SweepResult(
        variants=[
            SweepVariantResult(
                variant_id="v0",
                status="success",
                score=0.6,
                positive=PositiveControls(recovered_ids=_RECOVERED, missed_ids=_MISSED),
                negative=NegativeControls(admitted_ids=[], excluded_ids=_EXCLUDED),
            ),
            SweepVariantResult(variant_id="v1", status="failed", error="WDK refused"),
        ],
        best=None,
        search_name="GenesWithSignalPeptide",
        objective="f1",
    )
    deps.state.durable_result = DurableTaskResult(
        task_id=_TASK_ID,
        status="success",
        result=sweep.model_dump(by_alias=True, mode="json"),
    )

    await resolve_turn_resumption(state=deps.state, deps=deps)

    runs = deps.state.turn_markers.control_tests
    assert [(run.tool_call_id, run.origin) for run in runs] == [
        ("call_sweep:v0", "sweep")
    ]
    assert runs[0].evidence.positive == ControlSetEvidence(
        returned=_RECOVERED, not_returned=_MISSED
    )


async def test_a_failed_control_test_records_nothing() -> None:
    deps = _deps()
    deps.state.durable_result = DurableTaskResult(
        task_id=_TASK_ID, status="failed", error="WDK rejected step 440299573"
    )

    await resolve_turn_resumption(state=deps.state, deps=deps)

    assert deps.state.turn_markers.control_tests == []


async def test_a_search_level_test_is_recorded_on_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def measured(config: Any, **_controls: Any) -> ControlTestResult:
        del config
        return ControlTestResult(
            target=ControlTargetData(
                search_name="GenesByMolecularWeight", step_id=901, estimated_size=132
            ),
            positive=PositiveControls(recovered_ids=_RECOVERED, missed_ids=_MISSED),
            negative=NegativeControls(admitted_ids=[], excluded_ids=_EXCLUDED),
        )

    async def no_export(outcome: ControlOutcome, name: str) -> ControlOutcome:
        del name
        return outcome

    async def published(site_id: str, record_type: str, search: str) -> PublishedNames:
        del site_id, record_type, search
        return PublishedNames(label="Genes by Molecular Weight")

    async def knobs(site_id: str, record_type: str, search: str) -> list[str]:
        del site_id, record_type, search
        return []

    monkeypatch.setattr(experiment, "run_positive_negative_controls", measured)
    monkeypatch.setattr(experiment, "attach_control_downloads", no_export)
    monkeypatch.setattr(experiment, "published_names", published)
    monkeypatch.setattr(experiment, "tunable_parameters_of_search", knobs)
    ctx = agent_run_context(tool_call_id="call_search_controls")

    await experiment.run_control_tests_on_search(
        ctx,
        "GenesByMolecularWeight",
        {"organism": StringValue(value="Plasmodium falciparum 3D7")},
        positive_controls=[*_RECOVERED, *_MISSED],
        negative_controls=_EXCLUDED,
    )

    runs = ctx.deps.turn_markers.control_tests
    assert [run.tool_call_id for run in runs] == ["call_search_controls"]
    assert runs[0].evidence == _expected(None)
