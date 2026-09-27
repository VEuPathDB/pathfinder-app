"""The scripted assistant and the control-test wire two durable calls run on.

One model step makes three calls: two durable control tests of one saved set and
a sibling that settles in place. Only the model and the WDK read are doubles.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import tool_return_parts
from assistant_core.platform.db import async_session_factory
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

from pathfinder.ai.graph.runtime import AgentDeps, Context, VerificationScope
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.tools.standalone.experiment import run_control_tests_on_step
from pathfinder.assistants.pathfinder_spec import build_turn_context
from pathfinder.assistants.site_help.spec import (
    build_initial_state,
    charge_usage,
)
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.persistence.models import ControlSet
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID

TOOL = "run_control_tests_on_step"
STEP_A = 440230693
STEP_B = 440230653
CALL_A = "call_controls_a"
CALL_B = "call_controls_b"
CALL_PEEK = "call_peek"
POSITIVES = ["PF3D7_0102600"]
CONTROL_SET_ID = UUID("7c0a51e2-0000-4000-8000-0000000c0de5")


async def save_the_controls(user_id: UUID) -> None:
    """The saved set both control tests of the script name."""
    async with async_session_factory() as session:
        session.add(
            ControlSet(
                id=CONTROL_SET_ID,
                user_id=user_id,
                name="Kinase controls",
                site_id="plasmodb",
                record_type="transcript",
                positive_ids=POSITIVES,
                negative_ids=[],
            )
        )
        await session.commit()


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
            args={"wdk_step_id": STEP_A, "control_set_id": str(CONTROL_SET_ID)},
            tool_call_id=CALL_A,
        ),
        ToolCallPart(
            tool_name=TOOL,
            args={"wdk_step_id": STEP_B, "control_set_id": str(CONTROL_SET_ID)},
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


def _build_agent() -> Agent[AgentDeps, str]:
    return Agent(
        _build_mock(),
        output_type=str,
        deps_type=AgentDeps,
        instructions="Run the control tests the researcher asks for.",
        tools=[
            Tool(run_control_tests_on_step, sequential=True),
            Tool(peek_records),
        ],
        name="controls",
        defer_model_check=True,
    )


def _build_deps(state: TurnState, context: Context) -> AgentDeps:
    return AgentDeps(
        site_id=context.site_id,
        user_id=context.user_id,
        conversation_id=state.conversation_id,
        db_session_factory=context.db_session_factory,
        cancel_event=context.cancel_event,
        strategy_session=context.strategy_session,
        turn_markers=TurnMarkers(),
        verification_scope=VerificationScope(
            control_sets=[
                NamedControlSet(id=str(CONTROL_SET_ID), name="Kinase controls")
            ]
        ),
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
