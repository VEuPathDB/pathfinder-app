from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage, RunUsage, UsageLimits

from pathfinder.ai.lead.turn_budget import (
    TurnTokenBudget,
    counted_tokens,
    lead_turn_budget_message,
)

_CALLS = UsageLimits(request_limit=80, tool_calls_limit=80)


def test_a_cache_read_counts_a_tenth_of_a_fresh_token() -> None:
    spent = RunUsage(input_tokens=40_000, cache_read_tokens=30_000, output_tokens=500)

    assert counted_tokens(spent) == 10_000 + 3_000 + 500


def _calls_a_tool(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    return ModelResponse(
        parts=[
            ToolCallPart(tool_name="look", args={}, tool_call_id=f"c{len(messages)}")
        ],
        usage=RequestUsage(input_tokens=40_000, cache_read_tokens=36_000),
    )


def _run(limit: int) -> int:
    agent = Agent(
        FunctionModel(_calls_a_tool),
        capabilities=[TurnTokenBudget(limit=limit)],
    )
    looked: list[int] = []

    @agent.tool_plain
    def look() -> str:
        looked.append(1)
        return "seen"

    with pytest.raises(UsageLimitExceeded):
        asyncio.run(agent.run("go", usage_limits=UsageLimits(request_limit=20)))
    return len(looked)


def test_a_run_of_cached_calls_goes_on_past_the_raw_total() -> None:
    assert _run(limit=60_000) == 8


def test_the_budget_stops_before_the_call_that_would_pass_it() -> None:
    assert _run(limit=15_000) == 2


def test_a_stop_after_a_build_asks_to_continue() -> None:
    spent = RunUsage(input_tokens=700_000, requests=12)

    assert lead_turn_budget_message(
        spent, _CALLS, token_limit=600_000, built=True, checked=False
    ) == (
        "I stopped this turn at its budget of 600000 tokens. The strategy above is "
        "built but not yet checked. Say continue and I will check it and explain it."
    )


def test_a_stop_before_any_build_asks_to_narrow_the_request() -> None:
    spent = RunUsage(input_tokens=700_000, requests=12)

    assert lead_turn_budget_message(
        spent, _CALLS, token_limit=600_000, built=False, checked=False
    ) == (
        "I stopped this turn at its budget of 600000 tokens. "
        "Narrow the request and send it again, and I will start a fresh turn on it."
    )


def test_a_stop_at_the_call_limit_names_the_calls() -> None:
    spent = RunUsage(input_tokens=10_000, requests=80)

    assert lead_turn_budget_message(
        spent, _CALLS, token_limit=600_000, built=False, checked=False
    ).startswith("I stopped this turn at its budget of 80 model calls.")


def test_a_text_answer_is_never_stopped() -> None:
    def answers(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(
            parts=[TextPart(content="done")],
            usage=RequestUsage(input_tokens=900_000),
        )

    agent = Agent(FunctionModel(answers), capabilities=[TurnTokenBudget(limit=10)])

    assert asyncio.run(agent.run("go")).output == "done"
