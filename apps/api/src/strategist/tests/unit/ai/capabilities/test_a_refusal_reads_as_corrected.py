"""A call a guardrail refuses reads as corrected; a call the site fails reads as failed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from assistant_core.capabilities.refused_calls import CallRefused, MarkRefusedCalls
from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from pydantic_ai import Agent, RunContext, ToolFailed
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from strategist.ai.agents.tool_vocabulary import build_tool_repetition_guard
from strategist.ai.capabilities.read_once import ReadOnce
from strategist.ai.capabilities.site_reads import failed_read
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.platform.refusals import agent_capabilities


@dataclass
class _Deps:
    turn_markers: TurnMarkers = field(default_factory=TurnMarkers)
    tool_repetition_guard: ToolRepetitionGuard = field(
        default_factory=build_tool_repetition_guard
    )


def read_gene_record(ctx: RunContext[_Deps], gene_id: str) -> str:
    del ctx
    return f"{gene_id}: Polyphosphatase"


def _twice(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    made = sum(isinstance(m, ModelResponse) for m in messages)
    if made < 2:
        call = ToolCallPart("read_gene_record", {"gene_id": "g1"}, f"call_{made}")
        return ModelResponse(parts=[call])
    return ModelResponse(parts=[TextPart("done")])


def test_every_agent_marks_the_calls_its_tools_refuse() -> None:
    assert [
        type(capability)
        for capability in agent_capabilities([], toolsets=())
        if isinstance(capability, MarkRefusedCalls)
    ] == [MarkRefusedCalls]


def test_the_lead_marks_the_calls_it_refuses() -> None:
    leaves: list[AbstractCapability[Any]] = []
    build_lead_agent()._root_capability.apply(leaves.append)

    assert len([leaf for leaf in leaves if isinstance(leaf, MarkRefusedCalls)]) == 1


async def test_a_read_sent_again_is_refused_and_reads_as_corrected() -> None:
    agent: Agent[_Deps, str] = Agent(
        FunctionModel(_twice),
        deps_type=_Deps,
        toolsets=[FunctionToolset([read_gene_record])],
        capabilities=[
            ReadOnce[_Deps](reads=frozenset({"read_gene_record"})),
            MarkRefusedCalls[_Deps](),
        ],
    )

    result = await agent.run("read g1 twice", deps=_Deps())

    repeat = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ][1]
    assert repeat.outcome == "failed"
    assert [
        chunk.data for chunk in repeat.metadata or [] if isinstance(chunk, DataChunk)
    ] == [
        {
            "toolCallId": "call_1",
            "summary": (
                'read_gene_record answered these arguments in call call_0 ({"gene_id": '
                '"g1"}), and nothing has changed since, so it did'
            ),
            "status": "corrected",
        }
    ]


def test_a_site_that_fails_a_read_is_a_failure_and_not_a_refusal() -> None:
    failed = failed_read("read_gene_record", httpx.ConnectTimeout("no answer"))

    assert type(failed) is ToolFailed
    assert not isinstance(failed, CallRefused)
