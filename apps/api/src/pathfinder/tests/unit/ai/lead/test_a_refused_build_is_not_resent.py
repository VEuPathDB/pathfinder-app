from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from pydantic_ai.toolsets.abstract import AbstractToolset

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.dispatch_messages import option_binds_no_step_message
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.run_context import run_context_for

_SPEC = Path(__file__).with_name("singleton_genes_spec.json")
_LEFT_OUT = (
    "The build cannot place these criteria: c_singleton_genes (Transform Groups "
    "to Proteins) runs FromGroups, states no value and is not in the structure. "
    "Nothing was built and the strategy is unchanged. A criterion that runs a "
    "search of its own is a node of the structure: call set_structure again with "
    "a structure that includes c_singleton_genes, and drop_criterion on a "
    "criterion the strategy does not need."
)


def _spec() -> OperationalSpec:
    return OperationalSpec.model_validate_json(_SPEC.read_text())


def _lead_context() -> RunContext[LeadDeps]:
    runtime = Context(
        site_id="orthomcl",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="orthomcl"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="orthomcl",
        mode="strategy",
    )
    state.domain.operational_spec = _spec()
    deps = LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])
    return run_context_for(deps, "call_1")


async def _call(
    toolsets: list[AbstractToolset[LeadDeps]],
    ctx: RunContext[LeadDeps],
    name: str,
    args: dict[str, Any],
) -> None:
    for toolset in toolsets:
        tools = await toolset.get_tools(ctx)
        if name in tools:
            await toolset.call_tool(name, args, ctx, tools[name])
            return
    msg = f"no mounted toolset offers {name}"
    raise AssertionError(msg)


def test_a_left_out_criterion_that_states_no_value_is_named_with_its_remedy() -> None:
    assert option_binds_no_step_message(_spec(), ["c_singleton_genes"]) == _LEFT_OUT


@pytest.mark.asyncio
async def test_a_build_refused_before_a_read_is_not_sent_again() -> None:
    ctx = _lead_context()
    toolsets = list(build_lead_agent().toolsets)

    with pytest.raises(ModelRetry) as first:
        await _call(toolsets, ctx, "build_strategy", {})
    await _call(toolsets, ctx, "read_ledger_section", {"section": "build"})
    with pytest.raises(ToolFailed) as second:
        await _call(toolsets, ctx, "build_strategy", {})

    assert first.value.message == _LEFT_OUT
    assert second.value.message == (
        f"{_LEFT_OUT} This call was refused before with these arguments, and "
        "only reads ran since, so it did not run again."
    )
