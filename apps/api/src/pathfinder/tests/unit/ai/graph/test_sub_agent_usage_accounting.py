"""One dispatch reports the same tokens the turn counted for it."""

from __future__ import annotations

from decimal import Decimal

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import RunUsage

from pathfinder.ai.graph._lead_capture import _LeadRunCapture, absorb_sub_agent_usage
from pathfinder.ai.graph._lead_events import handle_sub_agent_event
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.sub_agent_tools import SubAgentCallUsage, SubAgentRunUsage
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_CALL_ID = "mock_frame_problem_cb4558c207"
_MODEL = "claude-sonnet-5"
_PROVIDER = "anthropic"


def _pass(tokens: int) -> SubAgentRunUsage:
    return SubAgentRunUsage(
        usage=RunUsage(input_tokens=tokens, output_tokens=0),
        model_name=_MODEL,
        provider_name=_PROVIDER,
        provider_url=None,
        parent_tool_call_id=_CALL_ID,
    )


def test_a_continued_dispatch_totals_every_pass_it_ran() -> None:
    """FRAME continues a budget-stopped pass under the same tool call id."""
    capture = _LeadRunCapture()

    absorb_sub_agent_usage(capture, _pass(2441))
    absorb_sub_agent_usage(capture, _pass(2441))

    spent = capture.sub_agent_usage_by_call[_CALL_ID]
    assert spent.tokens == 4882
    assert spent.tokens == capture.sub_agent_tokens
    assert spent.cost == capture.sub_agent_cost


def test_two_dispatches_keep_their_own_totals() -> None:
    capture = _LeadRunCapture()
    verify = SubAgentRunUsage(
        usage=RunUsage(input_tokens=80, output_tokens=0),
        model_name=_MODEL,
        provider_name=_PROVIDER,
        provider_url=None,
        parent_tool_call_id="mock_verify_strategy_cbd25d3576",
    )

    absorb_sub_agent_usage(capture, _pass(2441))
    absorb_sub_agent_usage(capture, verify)

    by_call = capture.sub_agent_usage_by_call
    assert by_call[_CALL_ID].tokens == 2441
    assert by_call["mock_verify_strategy_cbd25d3576"].tokens == 80
    assert capture.sub_agent_tokens == 2521


def test_the_completed_card_reports_what_the_dispatch_spent() -> None:
    """The thread's chip sums these cards, so each carries its whole dispatch."""
    capture = _LeadRunCapture()
    absorb_sub_agent_usage(capture, _pass(2441))
    absorb_sub_agent_usage(capture, _pass(2441))
    collector = ChunkCollector()
    deps = lead_deps(pipeline_state(user_prompt="create step"))
    calls: dict[str, str] = {}

    handle_sub_agent_event(
        deps,
        collector,
        FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name="frame_problem",
                args={"reason": "why"},
                tool_call_id=_CALL_ID,
            ),
        ),
        calls,
        capture.sub_agent_usage_by_call,
    )
    handle_sub_agent_event(
        deps,
        collector,
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="frame_problem",
                content=FrameResult(),
                tool_call_id=_CALL_ID,
            ),
        ),
        calls,
        capture.sub_agent_usage_by_call,
    )

    completed = [
        data
        for data in collector.data_of("data-sub-agent-call")
        if data["state"] == "completed"
    ]
    assert len(completed) == 1
    assert completed[0]["tokens"] == 4882
    assert Decimal(completed[0]["costUsd"]) == capture.sub_agent_cost


def test_a_dispatch_with_no_recorded_usage_reports_zero() -> None:
    assert SubAgentCallUsage().tokens == 0
    assert SubAgentCallUsage().cost == Decimal(0)
