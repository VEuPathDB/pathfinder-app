"""A read sent again with the same arguments runs once until any write of the turn."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset

from strategist.ai.capabilities.read_once import ReadOnce
from strategist.ai.graph.turn_records import TurnMarkers


@dataclass
class _Deps:
    steps: list[str] = field(default_factory=lambda: ["s1"])
    turn_markers: TurnMarkers = field(default_factory=TurnMarkers)
    reads: int = 0


def get_live_strategy_state(ctx: RunContext[_Deps]) -> str:
    ctx.deps.reads += 1
    return "steps=" + ",".join(ctx.deps.steps)


def create_eda_step(ctx: RunContext[_Deps]) -> str:
    ctx.deps.steps.append("eda")
    return "added"


def _scripted(calls: list[tuple[str, dict[str, str]]]) -> FunctionModel:
    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < len(calls):
            name, args = calls[made]
            return ModelResponse(parts=[ToolCallPart(name, args, f"call_{made}")])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(respond)


async def _returns(
    calls: list[tuple[str, dict[str, str]]], deps: _Deps
) -> list[ToolReturnPart]:
    agent = Agent(
        _scripted(calls),
        deps_type=_Deps,
        toolsets=[
            FunctionToolset([get_live_strategy_state]),
            FunctionToolset([create_eda_step]),
        ],
        capabilities=[ReadOnce[_Deps](reads=frozenset({"get_live_strategy_state"}))],
    )
    result = await agent.run("x", deps=deps)
    return [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


async def test_a_write_in_another_toolset_lets_the_read_run_again() -> None:
    deps = _Deps()
    parts = await _returns(
        [
            ("get_live_strategy_state", {}),
            ("create_eda_step", {}),
            ("get_live_strategy_state", {}),
        ],
        deps,
    )

    assert [(p.outcome, p.content) for p in parts] == [
        ("success", "steps=s1"),
        ("success", "added"),
        ("success", "steps=s1,eda"),
    ]


async def test_a_write_counted_on_the_turn_lets_the_read_run_again() -> None:
    deps = _Deps()

    def another_agent_writes(ctx: RunContext[_Deps]) -> str:
        ctx.deps.turn_markers.writes += 1
        return "a nested run wrote a step"

    agent = Agent(
        _scripted(
            [
                ("get_live_strategy_state", {}),
                ("another_agent_writes", {}),
                ("get_live_strategy_state", {}),
            ]
        ),
        deps_type=_Deps,
        toolsets=[FunctionToolset([get_live_strategy_state, another_agent_writes])],
        capabilities=[
            ReadOnce[_Deps](
                reads=frozenset({"get_live_strategy_state", "another_agent_writes"})
            )
        ],
    )

    await agent.run("x", deps=deps)

    assert deps.reads == 2


async def test_a_read_with_no_write_between_runs_once() -> None:
    deps = _Deps()
    parts = await _returns(
        [("get_live_strategy_state", {}), ("get_live_strategy_state", {})], deps
    )

    assert (deps.reads, [p.outcome for p in parts]) == (1, ["success", "failed"])
