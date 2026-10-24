from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from pathfinder.ai.audit.budget_stop import StopAtTheBudget, budget_stop_prose
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.reply import AuditReply

_LIMITS = UsageLimits(request_limit=5, tool_calls_limit=2)


def _three_calls(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    if len(messages) > 1:
        return ModelResponse(parts=[TextPart("the next turn answers")])
    calls = [
        ToolCallPart(tool_name="look", args={}, tool_call_id=f"c{k}") for k in range(3)
    ]
    return ModelResponse(parts=calls, model_name="judge")


def _agent(*, stopped: bool) -> Agent[AuditDeps, AuditReply | str]:
    agent = Agent(
        FunctionModel(_three_calls, model_name="judge"),
        deps_type=AuditDeps,
        output_type=[AuditReply, str],
        capabilities=[StopAtTheBudget()] if stopped else [],
    )

    @agent.tool_plain
    def look() -> str:
        return "seen"

    return agent


def _deps() -> AuditDeps:
    deps = AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())
    deps.recorded.extend([4, 5])
    return deps


async def test_a_run_past_its_tool_calls_ends_on_the_stop_reply() -> None:
    result = await _agent(stopped=True).run("judge", deps=_deps(), usage_limits=_LIMITS)

    assert result.output == AuditReply(prose=budget_stop_prose(2))
    last = result.response
    assert result.all_messages()[-1] == last
    assert (last.parts, last.model_name) == ([TextPart(budget_stop_prose(2))], "judge")


async def test_the_next_turn_runs_on_the_stopped_history() -> None:
    agent = _agent(stopped=True)
    first = await agent.run("judge", deps=_deps(), usage_limits=_LIMITS)

    second = await agent.run(
        "go on", deps=_deps(), message_history=first.all_messages()
    )

    assert second.output == "the next turn answers"


async def test_without_the_stop_the_limit_raises() -> None:
    with pytest.raises(UsageLimitExceeded):
        await _agent(stopped=False).run("judge", deps=_deps(), usage_limits=_LIMITS)


async def test_an_error_that_is_not_a_usage_limit_still_raises() -> None:
    agent = Agent(
        FunctionModel(_three_calls, model_name="judge"),
        deps_type=AuditDeps,
        output_type=[AuditReply, str],
        capabilities=[StopAtTheBudget()],
    )

    @agent.tool_plain
    def look() -> str:
        msg = "the read broke"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="the read broke"):
        await agent.run(
            "judge", deps=_deps(), usage_limits=UsageLimits(request_limit=5)
        )


def test_a_stop_with_no_verdict_says_none_was_stored() -> None:
    assert budget_stop_prose(0) == (
        "I stopped this turn at its limit of model requests and tool calls, before I "
        "finished, and I stored no verdict in this turn. Ask me again and I start "
        "from the findings."
    )


def test_the_stop_reply_counts_the_verdicts_it_kept() -> None:
    assert budget_stop_prose(1) == (
        "I stopped this turn at its limit of model requests and tool calls, before I "
        "finished. I stored 1 verdict in this turn, and each one is kept. Ask me to "
        "go on and I judge the findings that have no verdict yet."
    )
