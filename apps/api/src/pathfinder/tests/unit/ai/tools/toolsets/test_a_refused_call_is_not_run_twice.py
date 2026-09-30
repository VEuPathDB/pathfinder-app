"""A call refused and sent again with the same arguments, before any call ran,
fails without running and names the refusal; a third time it is the refusal
again, counted against the tool's retries."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.tools.toolsets._refusals import RefusalMemoryToolset

_REFUSAL = "limit must be between 1 and 100 (got 1000)."


@dataclass
class _Deps:
    turn_markers: TurnMarkers = field(default_factory=TurnMarkers)
    runs: list[int] = field(default_factory=list)


def _sample(ctx: RunContext[_Deps], limit: int) -> str:
    ctx.deps.runs.append(limit)
    if limit > 100:
        raise ModelRetry(_REFUSAL)
    return f"{limit} records"


def _strategy(ctx: RunContext[_Deps]) -> str:
    del ctx
    return "5 steps"


def _scripted(calls: list[tuple[str, dict[str, int]]]) -> FunctionModel:
    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < len(calls):
            name, args = calls[made]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(respond)


type _Answer = ToolReturnPart | RetryPromptPart


async def _run(calls: list[tuple[str, dict[str, int]]]) -> tuple[_Deps, list[_Answer]]:
    deps = _Deps()
    agent = Agent(
        _scripted(calls),
        deps_type=_Deps,
        toolsets=[
            RefusalMemoryToolset(
                wrapped=FunctionToolset([_sample, _strategy], max_retries=3)
            )
        ],
    )
    result = await agent.run("sample the step", deps=deps)
    parts: list[_Answer] = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    ]
    return deps, parts


@pytest.mark.asyncio
async def test_the_same_refused_call_fails_without_running() -> None:
    deps, parts = await _run(
        [("_sample", {"limit": 1000}), ("_sample", {"limit": 1000})]
    )

    assert deps.runs == [1000]
    first, second = parts
    assert isinstance(first, RetryPromptPart)
    assert isinstance(second, ToolReturnPart)
    assert second.outcome == "failed"
    assert second.content == (
        f"{_REFUSAL} This call was refused with these arguments and nothing ran "
        "since, so it did not run again."
    )


@pytest.mark.asyncio
async def test_a_third_identical_call_is_the_refusal_again() -> None:
    deps, parts = await _run([("_sample", {"limit": 1000})] * 3)

    assert deps.runs == [1000]
    assert [type(p).__name__ for p in parts] == [
        "RetryPromptPart",
        "ToolReturnPart",
        "RetryPromptPart",
    ]


@pytest.mark.asyncio
async def test_a_call_that_ran_in_between_lets_the_same_call_run_again() -> None:
    deps, parts = await _run(
        [
            ("_sample", {"limit": 1000}),
            ("_strategy", {}),
            ("_sample", {"limit": 1000}),
        ]
    )

    assert deps.runs == [1000, 1000]
    assert [type(p).__name__ for p in parts] == [
        "RetryPromptPart",
        "ToolReturnPart",
        "RetryPromptPart",
    ]


@pytest.mark.asyncio
async def test_other_arguments_run() -> None:
    deps, _ = await _run([("_sample", {"limit": 1000}), ("_sample", {"limit": 100})])

    assert deps.runs == [1000, 100]
    assert deps.turn_markers.refused_calls == []


@pytest.mark.asyncio
async def test_a_refusal_is_held_while_other_refusals_come_between() -> None:
    deps, parts = await _run(
        [
            ("_sample", {"limit": 1000}),
            ("_sample", {"limit": 500}),
            ("_sample", {"limit": 1000}),
        ]
    )

    assert deps.runs == [1000, 500]
    first, second, third = parts
    assert [type(first).__name__, type(second).__name__] == [
        "RetryPromptPart",
        "RetryPromptPart",
    ]
    assert isinstance(third, ToolReturnPart)
    assert third.outcome == "failed"
