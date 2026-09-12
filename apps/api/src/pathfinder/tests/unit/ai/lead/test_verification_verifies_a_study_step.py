"""Verification reaches a verdict on a study step instead of shrugging at it.

The step exports an EDA volcano, so its thresholds live in its
``eda_analysis_spec`` parameter and its strategy is addressed by the VEuPathDB
strategy id. Both are readable, so the digest reports the cut and succeeds.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import sub_agent_stream, sub_agent_tools
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.standalone.strategy_graph import StudyStepCheck
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.fixtures.builders import add_step_to_graph

_STEP_ID = "step_637b66c6"
_WDK_STEP_ID = 440186113
_WDK_STRATEGY_ID = 330558093
_DATASET_ID = "DS_e973eadd57"
_RECORD_COUNT = 1543

# The analysis document the step carries, in the shape the WDK bridge reads.
_ANALYSIS_SPEC = json.dumps(
    {
        "studyId": _DATASET_ID,
        "displayName": "Febrile vs normal",
        "description": "",
        "isPublic": False,
        "descriptor": {
            "subset": {"descriptor": [], "uiSettings": {}},
            "computations": [
                {
                    "computationId": "de2",
                    "descriptor": {
                        "type": "differentialexpression",
                        "configuration": {
                            "identifierVariable": {
                                "entityId": "ENT_fd574cd6",
                                "variableId": "VEUPATHDB_GENE_ID",
                            },
                            "valueVariable": {
                                "entityId": "ENT_fd574cd6",
                                "variableId": "SEQUENCE_READ_COUNT_ANTISENSE",
                            },
                            "comparator": {
                                "variable": {
                                    "entityId": "ENT_8151325d",
                                    "variableId": "VAR_081ab087",
                                },
                                "groupA": [{"label": "normal"}],
                                "groupB": [{"label": "febrile"}],
                            },
                            "differentialExpressionMethod": "DESeq",
                            "pValueFloor": "1e-200",
                        },
                    },
                    "visualizations": [
                        {
                            "visualizationId": "v2",
                            "displayName": "Volcano",
                            "descriptor": {
                                "type": "volcanoplot",
                                "configuration": {
                                    "effectSizeThreshold": 1,
                                    "significanceThreshold": 0.05,
                                },
                                "currentPlotFilters": [],
                            },
                        },
                    ],
                },
            ],
            "starredVariables": [],
            "dataTableConfig": {},
            "derivedVariables": [],
        },
    },
)


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("graph-1", "Heat shock", "plasmodb")
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(
            id=_STEP_ID,
            kind=StepKind.SEARCH,
            search_name="GenesByEdaVizWithCompute",
            display_name="Febrile vs normal",
            parameters={
                "eda_dataset_id": StringValue(value=_DATASET_ID),
                "eda_analysis_spec": StringValue(value=_ANALYSIS_SPEC),
            },
        ),
    )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={_STEP_ID: _WDK_STEP_ID},
        step_counts={_STEP_ID: _RECORD_COUNT},
        wdk_strategy_id=_WDK_STRATEGY_ID,
    )
    return session


def _deps(session: StrategySession) -> LeadDeps:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Genes at least 2-fold up or down with adjusted p below 0.05.",
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=session,
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=context, retrieved_memories=[])


def _called(messages: list[ModelMessage]) -> set[str]:
    return {
        part.tool_name
        for msg in messages
        if isinstance(msg, ModelResponse)
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    }


def _returned(messages: list[ModelMessage], tool_name: str) -> object | None:
    for msg in messages:
        if not isinstance(msg, ModelRequest):
            continue
        for part in msg.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                return part.content
    return None


def _digest_from(check: StudyStepCheck) -> dict[str, Any]:
    fold = check.fold_change_threshold
    significance = check.thresholds.significance_threshold if check.thresholds else None
    return {
        "digest": {
            "disposition": "done",
            "prose": (
                f"The step keeps {check.record_count:,} genes at "
                f"{fold:g}-fold and adjusted p {significance:g}."
            ),
            "reason": "The step's thresholds answer the request.",
            "success": all(entry.honored for entry in check.checks),
            "constraintReport": [
                entry.model_dump(by_alias=True, mode="json") for entry in check.checks
            ],
        },
    }


def _scripted(*, requested_fold_change: float) -> FunctionModel:
    """Read the strategy by its VEuPathDB id, check the step, then answer."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        already = _called(messages)
        if "get_strategy" not in already:
            return ToolCallPart(
                tool_name="get_strategy",
                args={"graph_id": str(_WDK_STRATEGY_ID), "summary_only": False},
                tool_call_id="call_get_strategy",
            )
        if "check_study_step" not in already:
            return ToolCallPart(
                tool_name="check_study_step",
                args={
                    "step_id": _STEP_ID,
                    "requested_fold_change": requested_fold_change,
                    "requested_significance": 0.05,
                },
                tool_call_id="call_check_study_step",
            )
        check = StudyStepCheck.model_validate(
            _returned(messages, "check_study_step"),
        )
        return ToolCallPart(
            tool_name="final_result",
            args=_digest_from(check),
            tool_call_id="call_final",
        )

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        return ModelResponse(parts=[_part(messages)])

    async def _stream(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del info
        part = _part(messages)
        yield {
            0: DeltaToolCall(
                name=part.tool_name,
                json_args=part.args_as_json_str(),
                tool_call_id=part.tool_call_id,
            ),
        }

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


class _Collector:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


@pytest.fixture(autouse=True)
def collector(monkeypatch: pytest.MonkeyPatch) -> _Collector:
    captured = _Collector()
    monkeypatch.setattr(sub_agent_stream, "get_stream_writer", lambda: captured)
    return captured


async def _verify(
    monkeypatch: pytest.MonkeyPatch,
    *,
    requested_fold_change: float,
) -> VerificationDelta:
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: _scripted(requested_fold_change=requested_fold_change),
    )
    deps = _deps(_session())
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Follow the script.",
    ):
        result = await run_verification(
            deps=deps,
            parent_tool_call_id="lead_call_verify",
            reason="confirm the study step's thresholds",
        )
    assert isinstance(result, VerificationDelta)
    return result


async def test_the_digest_reports_the_cut_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = await _verify(monkeypatch, requested_fold_change=2.0)

    assert delta.digest.success is True
    assert delta.digest.prose == (
        "The step keeps 1,543 genes at 2-fold and adjusted p 0.05."
    )
    assert [
        (c.label, c.requested, c.realized, c.honored)
        for c in (delta.digest.constraint_report)
    ] == [
        ("fold change", "2", "2", True),
        ("significance", "0.05", "0.05", True),
    ]


async def test_a_threshold_the_step_does_not_meet_fails_the_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = await _verify(monkeypatch, requested_fold_change=4.0)

    assert delta.digest.success is False
    unmet = [c for c in delta.digest.constraint_report if not c.honored]
    assert [(c.label, c.requested, c.realized) for c in unmet] == [
        ("fold change", "4", "2"),
    ]
