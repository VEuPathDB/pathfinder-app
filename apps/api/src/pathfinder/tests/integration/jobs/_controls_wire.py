"""The scripted assistant and the control-test wire two durable calls run on.

One model step makes three calls: two durable control tests and a sibling that
settles in place. Only the model and the WDK read are doubles.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import tool_return_parts
from assistant_core.spec import AssistantSpec
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.experiment import run_control_tests_on_step
from pathfinder.assistants.pathfinder_spec import build_turn_context
from pathfinder.assistants.site_help.spec import (
    build_initial_state,
    charge_usage,
)
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID

TOOL = "run_control_tests_on_step"
STEP_A = 440230693
STEP_B = 440230653
CALL_A = "call_controls_a"
CALL_B = "call_controls_b"
CALL_PEEK = "call_peek"
POSITIVES = ["PF3D7_0102600"]


class _Resumed(BaseModel):
    """What the completion turn hands back to one parked tool call."""

    model_config = ConfigDict(extra="ignore")

    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _prose_for(control_returns: list[ToolReturnPart]) -> str:
    recovered: list[str] = []
    for part in control_returns:
        resumed = _Resumed.model_validate(part.content)
        step = (resumed.result or {}).get("stepId", "none")
        recovered.append(f"{step}:{resumed.status}")
    return f"Controls ran on {', '.join(recovered)}."


def _script(messages: list[ModelMessage]) -> list[TextPart | ToolCallPart]:
    """Test both steps and peek at one, then quote both recoveries."""
    control_returns = [
        part for part in tool_return_parts(messages) if part.tool_name == TOOL
    ]
    if control_returns:
        return [TextPart(content=_prose_for(control_returns))]
    return [
        ToolCallPart(
            tool_name=TOOL,
            args={"wdk_step_id": STEP_A, "positive_controls": POSITIVES},
            tool_call_id=CALL_A,
        ),
        ToolCallPart(
            tool_name=TOOL,
            args={"wdk_step_id": STEP_B, "positive_controls": POSITIVES},
            tool_call_id=CALL_B,
        ),
        ToolCallPart(
            tool_name="peek_records",
            args={"wdk_step_id": STEP_A},
            tool_call_id=CALL_PEEK,
        ),
    ]


def _build_mock() -> FunctionModel:
    """A model whose one step makes three calls, then answers in prose."""

    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        return ModelResponse(parts=list(_script(messages)))

    async def _stream(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del info
        parts = _script(messages)
        text = [part for part in parts if isinstance(part, TextPart)]
        if text:
            yield text[0].content
            return
        yield {
            index: DeltaToolCall(
                name=part.tool_name,
                json_args=part.args_as_json_str(),
                tool_call_id=part.tool_call_id,
            )
            for index, part in enumerate(parts)
            if isinstance(part, ToolCallPart)
        }

    return FunctionModel(_respond, stream_function=_stream, model_name="scripted")


async def peek_records(ctx: RunContext[AgentDeps], wdk_step_id: int) -> str:
    """A non-durable sibling that settles inside the same model step."""
    del ctx
    return f"10 sample records from step {wdk_step_id}"


def _build_agent() -> Agent[LeadDeps, str]:
    return Agent(
        _build_mock(),
        output_type=str,
        deps_type=LeadDeps,
        instructions="Run the control tests the researcher asks for.",
        tools=[
            Tool(run_control_tests_on_step, sequential=True),
            Tool(peek_records),
        ],
        name="controls",
        defer_model_check=True,
    )


def _build_deps(state: TurnState, context: Context) -> LeadDeps:
    pipeline = PipelineState(
        conversation_id=state.conversation_id,
        user_id=state.user_id,
        site_id=state.site_id,
        mode=state.mode,
        user_prompt=state.user_prompt,
        domain=StrategyDomainState(),
    )
    return LeadDeps(
        state=pipeline,
        intent=None,
        runtime=context,
        retrieved_memories=[],
    )


def _build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, Context, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=Context,
        build_agent=_build_agent,
        build_deps=_build_deps,
        charge_usage=charge_usage,
    )


def build_spec() -> AssistantSpec:
    """Served under site help's id, so the turn needs no WDK identity."""
    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=_build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=_build_mock,
    )
