"""A ``set_structure`` call whose tree breaks a node's shape is a retry the model
reads, and the run goes on."""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_EMPTY_INTERSECT: dict[str, Any] = {
    "root": {"kind": "combine", "operator": "INTERSECT", "inputs": []}
}


def _retries(messages: list[ModelMessage]) -> list[RetryPromptPart]:
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


async def test_an_intersect_of_nothing_is_answered_with_the_combine_shape() -> None:
    seen: list[RetryPromptPart] = []

    def _model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        seen[:] = _retries(messages)
        if seen:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="final_result", args={"summary": "no tree to set"}
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="set_structure",
                    args=_EMPTY_INTERSECT,
                    tool_call_id="call_structure",
                )
            ]
        )

    deps = agent_deps_for(lead_deps(pipeline_state(user_prompt="drop the filter")))
    deps.db_session_factory = None
    agent = build_frame_agent()

    with agent.override(model=FunctionModel(_model)):
        result = await agent.run("drop the filter", deps=deps)

    assert isinstance(result.output, FrameResult)
    (retry,) = seen
    assert retry.tool_name == "set_structure"
    assert isinstance(retry.content, list)
    (error,) = retry.content
    assert error["msg"].startswith('Value error, a combine is {"kind": "combine"')
    assert error["msg"].endswith("with no criterion left, there is no tree to set.")
    assert "Fix the errors and try again." in retry.model_response()
    assert deps.agent_state.operational_spec_draft.structure is None
