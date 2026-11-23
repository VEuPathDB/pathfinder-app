from __future__ import annotations

import pytest
from pydantic_ai import Tool
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.toolsets import FunctionToolset

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead import sub_agent_stream
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.ai.lead.frame_dispatch import frame_work_order
from strategist.ai.lead.phase_stop import PhaseStopReason
from strategist.ai.lead.sub_agent_stops import ToolRefusal, early_stop
from strategist.ai.lead.sub_agent_stream import PhaseRun, stream_sub_agent
from strategist.ai.lead.sub_agent_tools import SubAgentRunUsage
from strategist.tests._support.sub_agents import pinned_sub_agent
from strategist.tests.unit.ai.lead.conftest import (
    called_tool_names,
    lead_deps,
    pipeline_state,
    tool_script_model,
)
from strategist.tests.unit.ai.lead.test_sub_agent_stream_stops import (
    needs_int,
    refuse_always,
)

pytestmark = pytest.mark.usefixtures("collector")

_SPENT_ON_A = UnexpectedModelBehavior(
    "Tool 'a' exceeded max retries count of 3. Consider raising the retry limit."
)


def test_a_budget_spent_on_one_tool_names_it_not_the_last_refused() -> None:
    refused_b = ToolRefusal(tool_name="b", text="b refused.")
    refused_a = ToolRefusal(tool_name="a", text="a refused.")

    stop = early_stop(_SPENT_ON_A, {"a": refused_a, "b": refused_b})

    assert stop is not None
    assert (stop.reason, stop.refusal) == (PhaseStopReason.TOOL_RETRIES, refused_a)


def test_a_budget_spent_on_a_tool_with_no_refusal_still_names_it() -> None:
    stop = early_stop(_SPENT_ON_A, {"b": ToolRefusal(tool_name="b", text="no.")})

    assert stop is not None
    assert stop.refusal == ToolRefusal(tool_name="a", text="")


def _a_then_b(messages: list[ModelMessage]) -> ToolCallPart:
    made = len(called_tool_names(messages))
    if made % 2:
        return ToolCallPart(
            tool_name="refuse_always", args="{}", tool_call_id=f"b{made}"
        )
    return ToolCallPart(
        tool_name="needs_int", args={"count": "many"}, tool_call_id=f"a{made}"
    )


async def test_a_pass_stopped_on_one_tool_after_another_refused_names_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sub_agent_stream, "phase_override_kwargs", lambda runtime, role: {}
    )
    usage_log: list[SubAgentRunUsage] = []
    deps = lead_deps(
        pipeline_state(user_prompt="Find the kinases."), record_usage=usage_log.append
    )
    toolset = FunctionToolset[AgentDeps](tools=[Tool(needs_int), Tool(refuse_always)])

    with pinned_sub_agent(
        monkeypatch,
        "frame",
        model=tool_script_model(_a_then_b),
        toolsets=[toolset],
        instructions="Call the tools.",
    ):
        await stream_sub_agent(
            run=PhaseRun("frame", frame_work_order("bind them", deps), 8),
            agent_deps=agent_deps_for(deps, call_id="call_test"),
            parent_tool_call_id="call_frame_1",
            expected_output_type=FrameResult,
            deps=deps,
        )

    stop = deps.last_phase_stop
    assert stop is not None
    assert (stop.reason, stop.tool_name) == (PhaseStopReason.TOOL_RETRIES, "needs_int")
    assert [u.parent_tool_call_id for u in usage_log] == ["call_frame_1"]
