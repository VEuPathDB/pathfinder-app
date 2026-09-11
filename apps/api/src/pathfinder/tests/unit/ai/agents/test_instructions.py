"""The run's budget is disclosed to the model that spends it.

``UsageLimits`` bound every run, and nothing showed the model what it had
left. The meter renders the run's own ceiling from the context the run
already carries.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.agents._instructions import pinned_run_budget
from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.instructions import pinned_instructions

_LIMITS = UsageLimits(
    request_limit=10, tool_calls_limit=80, total_tokens_limit=4_000_000
)


def _ctx(usage: RunUsage, limits: UsageLimits | None) -> RunContext[None]:
    return RunContext(deps=None, model=TestModel(), usage=usage, usage_limits=limits)


def test_the_meter_names_both_ceilings_and_what_is_spent() -> None:
    rendered = pinned_run_budget(
        _ctx(RunUsage(tool_calls=7, input_tokens=120_000, output_tokens=5_000), _LIMITS)
    )
    assert rendered is not None
    assert "tools 7/80" in rendered
    assert "tokens 125,000/4,000,000" in rendered


def test_the_meter_is_empty_when_the_run_enforces_no_limits() -> None:
    """A bare context is not backed by a run, so there is no budget to report."""
    unlimited = pinned_run_budget(_ctx(RunUsage(tool_calls=3), None))
    limited = pinned_run_budget(_ctx(RunUsage(tool_calls=3), _LIMITS))
    assert (unlimited, limited is None) == (None, False)


def test_the_meter_reports_only_the_ceilings_the_run_sets() -> None:
    rendered = pinned_run_budget(
        _ctx(RunUsage(tool_calls=2), UsageLimits(tool_calls_limit=9))
    )
    assert rendered is not None
    assert "tools 2/9" in rendered
    assert "tokens" not in rendered


def test_a_run_with_only_a_request_limit_renders_nothing() -> None:
    requests_only = pinned_run_budget(_ctx(RunUsage(), UsageLimits(request_limit=4)))
    tools_too = pinned_run_budget(_ctx(RunUsage(), UsageLimits(tool_calls_limit=4)))
    assert (requests_only, tools_too is None) == (None, False)


async def test_the_meter_moves_between_steps_of_one_run() -> None:
    """The card's pin: the model sees the counter change as it spends."""
    seen: list[str] = []

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        request = messages[-1]
        assert isinstance(request, ModelRequest)
        seen.append(request.instructions or "")
        if len(seen) == 1:
            return ModelResponse(parts=[ToolCallPart("spend", {})])
        return ModelResponse(parts=[TextPart("done")])

    agent: Agent[None, str] = Agent(FunctionModel(_fn))
    agent.instructions(pinned_run_budget)

    @agent.tool_plain
    def spend() -> str:
        return "spent"

    await agent.run(
        "go",
        usage_limits=UsageLimits(request_limit=5, tool_calls_limit=6),
    )
    assert len(seen) == 2
    assert "tools 0/6" in seen[0]
    assert "tools 1/6" in seen[1]


def test_every_agent_that_runs_under_a_limit_pins_the_meter() -> None:
    for build in (
        build_lead_agent,
        build_frame_agent,
        build_execution_agent,
        build_verification_agent,
    ):
        assert "pinned_run_budget" in pinned_instructions(build())


def _lead_ctx(usage: RunUsage, limits: UsageLimits) -> RunContext[LeadDeps]:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="which kinases matter",
    )
    runtime = Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    deps = LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=usage,
        usage_limits=limits,
    )


def test_a_lead_tool_reads_the_budget_of_the_run_that_called_it() -> None:
    """The narrowed context a Lead tool takes is the same run, budget included."""
    outer = _lead_ctx(RunUsage(tool_calls=4), UsageLimits(tool_calls_limit=80))
    inner = inner_context(outer)
    assert inner.usage is outer.usage
    assert inner.usage_limits is outer.usage_limits
    assert pinned_run_budget(inner) == pinned_run_budget(outer)
