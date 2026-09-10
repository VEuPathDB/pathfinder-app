"""Builders the Lead unit tests share: deps, runtime, scripted models, capture."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import sub_agent_stream
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentRunUsage

PartFor = Callable[[list[ModelMessage]], ToolCallPart | list[ToolCallPart]]


def never_db_factory() -> AsyncSession:
    msg = "db factory should not be called in unit tests"
    raise AssertionError(msg)


def lead_runtime(
    site_id: str = "plasmodb",
    *,
    strategy_session: StrategySession | None = None,
    user_id: UUID | None = None,
) -> Context:
    return Context(
        site_id=site_id,
        user_id=user_id if user_id is not None else uuid4(),
        strategy_session=(
            strategy_session
            if strategy_session is not None
            else StrategySession(site_id=site_id)
        ),
        db_session_factory=never_db_factory,
        cancel_event=asyncio.Event(),
    )


def pipeline_state(
    site_id: str = "plasmodb",
    *,
    user_prompt: str = "",
    user_message_id: UUID | None = None,
    domain: StrategyDomainState | None = None,
) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id=site_id,
        mode="strategy",
        user_prompt=user_prompt,
        user_message_id=user_message_id,
        domain=domain if domain is not None else StrategyDomainState(),
    )


def lead_deps(
    state: PipelineState,
    *,
    intent: UserIntent | None = None,
    strategy_session: StrategySession | None = None,
    record_usage: Callable[[SubAgentRunUsage], None] | None = None,
) -> LeadDeps:
    runtime = lead_runtime(
        state.site_id,
        strategy_session=strategy_session,
        user_id=state.user_id,
    )
    deps = LeadDeps(
        state=state,
        intent=intent,
        runtime=runtime,
        retrieved_memories=[],
    )
    if record_usage is not None:
        deps.record_sub_agent_usage = record_usage
    return deps


def lead_run_context(
    deps: LeadDeps,
    tool_call_id: str | None = None,
) -> RunContext[LeadDeps]:
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id=tool_call_id,
    )


def session_with_one_step(
    site_id: str = "plasmodb",
    *,
    name: str = "Kinases",
    step_id: str = "step_a",
) -> StrategySession:
    session = StrategySession(site_id=site_id)
    graph = StrategyGraph(graph_id="g1", name=name, site_id=site_id)
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id=step_id, search_name="GenesByText"),
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def user_intent(
    raw_text: str,
    classification: IntentClassification,
    *,
    inferred_goal: str = "what the user asked for",
    explicit_constraints: list[Constraint] | None = None,
) -> UserIntent:
    return UserIntent(
        raw_text=raw_text,
        classification=classification,
        inferred_goal=inferred_goal,
        explicit_constraints=list(explicit_constraints or []),
    )


def requirement(kind: ConstraintKind, label: str, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        label=label,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


class ChunkCollector:
    """Stands in for the langgraph stream writer."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)

    @property
    def chunks(self) -> list[dict[str, Any]]:
        return [p["chunk"] for p in self.payloads if "chunk" in p]

    def chunks_of(self, chunk_type: str) -> list[dict[str, Any]]:
        return [c for c in self.chunks if c.get("type") == chunk_type]

    def data_of(self, chunk_type: str) -> list[dict[str, Any]]:
        return [c["data"] for c in self.chunks_of(chunk_type)]

    def step_tool_names(self) -> set[str]:
        return {
            data["toolName"]
            for data in self.data_of("data-sub-agent-step")
            if data.get("toolName")
        }


@pytest.fixture
def collector(monkeypatch: pytest.MonkeyPatch) -> ChunkCollector:
    """A collector installed as the sub-agent stream writer."""
    captured = ChunkCollector()
    monkeypatch.setattr(sub_agent_stream, "get_stream_writer", lambda: captured)
    return captured


class OfferedTools:
    """The tool names the model was offered, one entry per model step."""

    def __init__(self) -> None:
        self.steps: list[frozenset[str]] = []

    def record(self, info: AgentInfo) -> int:
        self.steps.append(frozenset(tool.name for tool in info.function_tools))
        return len(self.steps)


def called_tool_names(messages: list[ModelMessage]) -> set[str]:
    return {
        part.tool_name
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }


def tool_script_model(part_for: PartFor) -> FunctionModel:
    """A model whose every step is the tool call(s) ``part_for`` names."""

    def _parts(messages: list[ModelMessage]) -> list[ToolCallPart]:
        produced = part_for(messages)
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


def final_result_part(args: dict[str, Any]) -> ToolCallPart:
    return ToolCallPart(
        tool_name="final_result",
        args=args,
        tool_call_id=f"call_final_{uuid4().hex[:8]}",
    )


def final_result_model(args: dict[str, Any]) -> FunctionModel:
    """A model that answers with the agent's typed output straight away."""
    return tool_script_model(lambda _messages: final_result_part(args))


def call_then_final_model(
    tool_name: str,
    tool_args: dict[str, Any],
    final_args: dict[str, Any],
) -> FunctionModel:
    """Call ``tool_name`` once, then emit the agent's typed output."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if tool_name in called_tool_names(messages):
            return final_result_part(final_args)
        return ToolCallPart(
            tool_name=tool_name,
            args=tool_args,
            tool_call_id=f"call_{tool_name}",
        )

    return tool_script_model(_part)


def endless_tool_call_model(tool_name: str) -> FunctionModel:
    """A model that calls one tool on every step and never finishes."""
    return tool_script_model(
        lambda _messages: ToolCallPart(
            tool_name=tool_name,
            args="{}",
            tool_call_id=uuid4().hex,
        ),
    )
