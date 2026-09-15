"""The scripted Lead run and the approval-gated sub-agent its tests drive."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import FunctionToolset
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import sub_agent_stream
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.sub_agents import pinned_sub_agent

OPTIMIZE_ARGS: dict[str, Any] = {
    "target": {
        "site_id": "plasmodb",
        "record_type": "transcript",
        "search_name": "GenesByRNASeqEvidence",
        "parameter_space": [
            {"name": "min_fold_change", "kind": "numeric", "low": 1.5, "high": 4.0},
        ],
    },
    "controls": {
        "positive_controls": ["PF3D7_1133400"],
        "negative_controls": ["PF3D7_0930300"],
    },
    "settings": {"budget": 8, "objective": "f1"},
}
VERIFICATION_FINAL: dict[str, Any] = {
    "digest": {
        "disposition": "done",
        "prose": "scripted",
        "reason": "scripted",
        "success": True,
    },
}
RECOVERY_FINAL: dict[str, Any] = {
    "actionsTaken": ["deleted s2"],
    "followUpNeeded": False,
}
LEAD_FINAL: dict[str, Any] = {
    "prose": "scripted",
    "nextState": "await_user",
    "strategyChanged": False,
}

TEST_INSTRUCTIONS = "Call the tool the script names, then return the typed output."


def tool_calls(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return [
        part
        for msg in messages
        if isinstance(msg, ModelResponse)
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    ]


def _user_prompts(messages: list[ModelMessage]) -> list[str]:
    return [
        part.content
        for msg in messages
        if isinstance(msg, ModelRequest)
        for part in msg.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]


def scripted_model(
    part_for: Any, seen_prompts: list[str] | None = None
) -> FunctionModel:
    """A FunctionModel driven by ``part_for(messages) -> list[ToolCallPart]``."""

    def _parts(messages: list[ModelMessage]) -> list[ToolCallPart]:
        if seen_prompts is not None:
            seen_prompts.extend(_user_prompts(messages))
        produced: ToolCallPart | list[ToolCallPart] = part_for(messages)
        return produced if isinstance(produced, list) else [produced]

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        return ModelResponse(parts=list(_parts(messages)))

    async def _stream(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del info
        yield {
            index: DeltaToolCall(
                name=part.tool_name,
                json_args=part.args_as_json_str(),
                tool_call_id=part.tool_call_id,
            )
            for index, part in enumerate(_parts(messages))
        }

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def one_call_model(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    final_args: dict[str, Any],
    seen_prompts: list[str] | None = None,
) -> FunctionModel:
    """Call ``tool_name`` once, then emit the agent's typed output."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if tool_name not in {c.tool_name for c in tool_calls(messages)}:
            return ToolCallPart(
                tool_name=tool_name,
                args=tool_args,
                tool_call_id=f"call_{tool_name}",
            )
        return ToolCallPart(
            tool_name="final_result",
            args=final_args,
            tool_call_id=f"call_final_{uuid4().hex[:8]}",
        )

    return scripted_model(_part, seen_prompts)


def two_delete_model() -> FunctionModel:
    """Ask to delete one step, then another, then finish."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        deletes = [c for c in tool_calls(messages) if c.tool_name == "delete_step"]
        if len(deletes) < 2:
            index = len(deletes) + 1
            return ToolCallPart(
                tool_name="delete_step",
                args={"step_id": f"s{index}"},
                tool_call_id=f"call_delete_{index}",
            )
        return ToolCallPart(
            tool_name="final_result",
            args=RECOVERY_FINAL,
            tool_call_id=f"call_final_{uuid4().hex[:8]}",
        )

    return scripted_model(_part)


class Collector:
    """Stands in for the langgraph stream writer."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)

    def chunks_of(self, chunk_type: str) -> list[dict[str, Any]]:
        return [
            p["chunk"]
            for p in self.payloads
            if "chunk" in p and p["chunk"].get("type") == chunk_type
        ]


def _quota_offline() -> AsyncSession:
    """Quota accumulation tolerates a database that is not there."""
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def lead_state() -> PipelineState:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Tune the RNA-Seq fold change against my controls.",
        user_message_id=uuid4(),
    )
    # A recovery dispatch answers a build that failed, so the state carries one.
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        failed_steps=[
            StepPushFailure(
                step_id="s2",
                search_name="GenesByRNASeqEvidence",
                error="422 min_fold_change: Invalid value",
            ),
        ],
        root_count=0,
    )
    return state


def lead_deps(state: PipelineState) -> LeadDeps:
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_quota_offline,
        cancel_event=asyncio.Event(),
    )
    # The dispatch tools reach the model only on a turn that classified a
    # request to build.
    state.turn_markers.intent_classified = True
    return LeadDeps(
        state=state,
        intent=UserIntent(
            classification=IntentClassification.EXTEND_STRATEGY,
            inferred_goal="tune the fold change",
        ),
        runtime=context,
        retrieved_memories=[],
    )


async def drive_lead(
    *,
    state: PipelineState,
    deps: LeadDeps,
    writer: Collector,
) -> _LeadRunCapture:
    capture = _LeadRunCapture()
    await _drive_lead_stream(
        state=state,
        agent=build_lead_agent(),
        deps=deps,
        capture=capture,
        writer=writer,
        message_id=uuid4(),
    )
    return capture


@contextmanager
def pinned_verification_agent(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The verification agent, mounting its real approval-gated toolset."""
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions=TEST_INSTRUCTIONS,
    ):
        yield


@pytest.fixture
def writer(monkeypatch: pytest.MonkeyPatch) -> Collector:
    captured = Collector()
    monkeypatch.setattr(sub_agent_stream, "get_stream_writer", lambda: captured)
    return captured


@pytest.fixture
def deleted_step_ids() -> list[str]:
    return []


@pytest.fixture
def stub_execution_toolset(
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> Iterator[None]:
    """The execution agent with one approval-gated tool that records its calls."""

    async def delete_step(ctx: RunContext[AgentDeps], step_id: str) -> str:
        del ctx
        deleted_step_ids.append(step_id)
        return f"deleted {step_id}"

    toolset = FunctionToolset[AgentDeps](
        tools=[Tool(delete_step, requires_approval=True)],
    )
    with pinned_sub_agent(
        monkeypatch,
        "execution",
        toolsets=[toolset],
        instructions=TEST_INSTRUCTIONS,
    ):
        yield


def script_lead(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    seen_prompts: list[str] | None = None,
) -> None:
    monkeypatch.setattr(
        _lead_model,
        "get_mock_model",
        lambda: one_call_model(
            tool_name=tool_name,
            tool_args={"reason": "scripted dispatch"},
            final_args=LEAD_FINAL,
            seen_prompts=seen_prompts,
        ),
    )


def consult_and_dispatch_model() -> FunctionModel:
    """One response that both asks the user a question and dispatches a sub-agent."""

    def _parts(messages: list[ModelMessage]) -> list[ToolCallPart]:
        names = {c.tool_name for c in tool_calls(messages)}
        if "recover_failed_steps" not in names:
            return [
                ToolCallPart(
                    tool_name="consult_user",
                    args={"questions": [{"id": "q1", "prompt": "Which step?"}]},
                    tool_call_id="call_consult",
                ),
                ToolCallPart(
                    tool_name="recover_failed_steps",
                    args={"reason": "drop the failed step"},
                    tool_call_id="call_recover_failed_steps",
                ),
            ]
        return [
            ToolCallPart(
                tool_name="final_result",
                args=LEAD_FINAL,
                tool_call_id=f"call_final_{uuid4().hex[:8]}",
            ),
        ]

    return scripted_model(_parts)
