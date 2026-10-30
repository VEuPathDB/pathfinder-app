from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.separation import TooFewControls

from pathfinder.ai.lead.lead_agent import LEAD_MODEL, build_lead_toolset
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.read_facts import ReadFact, ReadRow
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_POSITIVES = ["PF3D7_0213400", "PF3D7_0321400", "PF3D7_0902300", "PF3D7_1123100"]
_NEGATIVES = ["PF3D7_1133400", "PF3D7_0304600"]
_THIRD_NEGATIVE = "PF3D7_1246200"
_ANSWER: dict[str, Any] = {
    "prose": "Send me more controls and I will run the separation.",
    "nextState": "await_user",
}


def _run_call(negatives: list[str]) -> ToolCallPart:
    return ToolCallPart(
        tool_name="separate_controls",
        args={
            "reply": "I will measure your controls against the site's searches.",
            "positive_controls": _POSITIVES,
            "negative_controls": negatives,
            "mode": "exact",
        },
        tool_call_id="call_separate",
    )


def _refusals(messages: list[ModelMessage]) -> list[str]:
    return [
        part.model_response()
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


async def _turn(
    negatives: list[str],
) -> tuple[LeadResponse | DeferredToolRequests, LeadDeps, list[str]]:
    told: list[str] = []

    def _model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        told[:] = _refusals(messages)
        if told:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="final_result", args=_ANSWER)]
            )
        return ModelResponse(parts=[_run_call(negatives)])

    agent: Agent[LeadDeps, LeadResponse | DeferredToolRequests] = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        toolsets=[build_lead_toolset()],
        defer_model_check=True,
    )
    deps = lead_deps(pipeline_state(user_prompt="Find a strategy that separates them."))
    result = await agent.run(
        "Find a strategy that separates them.", deps=deps, model=FunctionModel(_model)
    )
    return result.output, deps, told


async def test_four_positives_and_two_negatives_are_refused_before_the_card() -> None:
    output, deps, told = await _turn(_NEGATIVES)

    assert output == LeadResponse.model_validate(_ANSWER)
    assert len(told) == 1
    assert told[0].startswith(
        "With 4 positive and 2 negative controls, the best any search can reach "
        "is p = 0.067, and a result needs p under 0.05. Add 1 more negative "
        "control or 1 more positive control. Nothing was started and no card "
        "was shown."
    )
    assert deps.turn_markers.too_few_controls == TooFewControls(
        positives=4, negatives=2
    )


async def test_a_third_negative_reaches_the_card() -> None:
    output, deps, told = await _turn([*_NEGATIVES, _THIRD_NEGATIVE])

    assert isinstance(output, DeferredToolRequests)
    assert [call.tool_call_id for call in output.approvals] == ["call_separate"]
    assert (told, deps.turn_markers.too_few_controls) == ([], None)


async def test_the_facts_beside_the_reply_ask_for_more_controls() -> None:
    _, deps, _ = await _turn(_NEGATIVES)

    facts = turn_facts(deps)

    assert facts.reads == [
        ReadFact(
            title="Too few controls for any search to beat chance",
            rows=[
                ReadRow(label="positive controls", value="4"),
                ReadRow(label="negative controls", value="2"),
                ReadRow(label="best p-value any search can reach", value="0.067"),
                ReadRow(label="a result needs p under", value="0.05"),
                ReadRow(label="negative controls to add", value="1"),
                ReadRow(label="or positive controls to add", value="1"),
            ],
        )
    ]
    assert facts.holds_site_data()
