"""A sweep call the worker would refuse is refused before its card is drawn."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.ai.lead.lead_agent import LEAD_MODEL, build_sweep_toolset
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.ai.tools.standalone import optimization
from pathfinder.ai.tools.standalone.optimization import sweep_can_run
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import session_with

_SAVED_SET_ID = "96eaafb0-659c-4041-8bf3-5c66e5a9f95c"
_NO_CONTROLS: dict[str, Any] = {
    "reply": "I will sweep the SignalP version against your controls.",
    "wdk_step_id": 440606243,
    "parameters": ["signalp_version"],
    "budget": 30,
}
_ANSWER: dict[str, Any] = {
    "prose": "Paste the control ids and I will run the sweep.",
    "nextState": "await_user",
    "strategyChanged": False,
}


def _refusals(messages: list[ModelMessage]) -> list[str]:
    return [
        part.model_response()
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


async def test_a_sweep_with_no_controls_never_reaches_a_card() -> None:
    told: list[str] = []

    def _model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        told[:] = _refusals(messages)
        if told:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="final_result", args=_ANSWER)]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="optimize_search_parameters",
                    args=_NO_CONTROLS,
                    tool_call_id="call_sweep",
                )
            ]
        )

    agent: Agent[LeadDeps, LeadResponse | DeferredToolRequests] = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        toolsets=[build_sweep_toolset()],
        defer_model_check=True,
    )
    deps = lead_deps(pipeline_state(user_prompt="Optimize the SignalP version."))

    result = await agent.run(
        "Optimize the SignalP version.", deps=deps, model=FunctionModel(_model)
    )

    assert isinstance(result.output, LeadResponse)
    assert len(told) == 1
    assert "control_set_id" in told[0]
    assert "Field required" in told[0]


async def test_a_parameter_named_by_its_label_is_refused_before_the_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _tunable(site_id: str, record_type: str, search_name: str) -> list[str]:
        assert (site_id, record_type, search_name) == (
            "plasmodb",
            "transcript",
            "GenesWithSignalPeptide",
        )
        return ["organism", "signalp_version"]

    monkeypatch.setattr(optimization, "tunable_parameters_of_search", _tunable)
    session = session_with(
        StrategyStepNode(id="step_sp", search_name="GenesWithSignalPeptide"),
        {"step_sp": 440649693},
    )
    ctx = lead_run_context(strategy_session=session)
    ctx.deps.state.domain.attach_control_set(
        NamedControlSet(id=_SAVED_SET_ID, name="Signal peptide controls")
    )

    with pytest.raises(ModelRetry) as raised:
        await sweep_can_run(
            ctx,
            wdk_step_id=440649693,
            control_set_id=_SAVED_SET_ID,
            parameters=["SignalP version"],
            reply="I will make this change and report what it takes with it.",
        )

    assert str(raised.value) == (
        "GenesWithSignalPeptide cannot vary SignalP version. Name the parameters "
        "as the search names them: organism, signalp_version. Nothing was "
        "started and no card was shown."
    )


async def test_a_saved_control_set_is_controls_enough_for_the_card() -> None:
    call = ToolCallPart(
        tool_name="optimize_search_parameters",
        args={**_NO_CONTROLS, "control_set_id": _SAVED_SET_ID},
        tool_call_id="call_sweep",
    )

    def _model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[call])

    agent: Agent[LeadDeps, LeadResponse | DeferredToolRequests] = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        toolsets=[build_sweep_toolset()],
        defer_model_check=True,
    )
    deps = lead_deps(pipeline_state(user_prompt="Sweep it on my saved controls."))
    deps.state.domain.attach_control_set(
        NamedControlSet(id=_SAVED_SET_ID, name="Signal peptide controls")
    )

    result = await agent.run(
        "Sweep it on my saved controls.", deps=deps, model=FunctionModel(_model)
    )

    assert isinstance(result.output, DeferredToolRequests)
    assert [c.tool_call_id for c in result.output.approvals] == ["call_sweep"]


async def test_typed_control_ids_are_no_control_set() -> None:
    told: list[str] = []
    typed = {
        **_NO_CONTROLS,
        "positive_controls": ["PF3D7_0100600"],
        "negative_controls": ["PF3D7_0111300"],
    }

    def _model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        told[:] = _refusals(messages)
        if told:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="final_result", args=_ANSWER)]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="optimize_search_parameters",
                    args=typed,
                    tool_call_id="call_sweep",
                )
            ]
        )

    agent: Agent[LeadDeps, LeadResponse | DeferredToolRequests] = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        toolsets=[build_sweep_toolset()],
        defer_model_check=True,
    )
    deps = lead_deps(pipeline_state(user_prompt="Optimize the SignalP version."))

    result = await agent.run(
        "Optimize the SignalP version.", deps=deps, model=FunctionModel(_model)
    )

    assert isinstance(result.output, LeadResponse)
    assert len(told) == 1
    assert "control_set_id" in told[0]
    assert "positive_controls" in told[0]
