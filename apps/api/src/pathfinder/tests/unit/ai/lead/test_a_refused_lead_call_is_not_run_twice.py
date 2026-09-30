"""A Lead tool call refused and sent again with the same arguments, before any
call ran, fails without running."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from pydantic_ai.toolsets.abstract import AbstractToolset

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.strategy_rename import NO_STRATEGY
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.run_context import run_context_for


def _lead_context() -> RunContext[LeadDeps]:
    runtime = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )
    deps = LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])
    return run_context_for(deps, "call_1")


async def _mounted(name: str, ctx: RunContext[LeadDeps]) -> AbstractToolset[LeadDeps]:
    for toolset in build_lead_agent().toolsets:
        if name in await toolset.get_tools(ctx):
            return toolset
    msg = f"no mounted toolset offers {name}"
    raise AssertionError(msg)


async def _call(
    toolset: AbstractToolset[LeadDeps], ctx: RunContext[LeadDeps], args: dict[str, Any]
) -> None:
    tools = await toolset.get_tools(ctx)
    await toolset.call_tool("rename_strategy", args, ctx, tools["rename_strategy"])


@pytest.mark.asyncio
async def test_a_refused_lead_call_sent_again_fails_and_a_third_is_refused() -> None:
    ctx = _lead_context()
    toolset = await _mounted("rename_strategy", ctx)
    args = {"name": "Secreted kinases"}

    with pytest.raises(ModelRetry) as first:
        await _call(toolset, ctx, args)
    with pytest.raises(ToolFailed) as second:
        await _call(toolset, ctx, args)
    with pytest.raises(ModelRetry) as third:
        await _call(toolset, ctx, args)

    assert first.value.message == NO_STRATEGY
    assert second.value.message == (
        f"{NO_STRATEGY} This call was refused with these arguments and nothing "
        "ran since, so it did not run again."
    )
    assert third.value.message == NO_STRATEGY
