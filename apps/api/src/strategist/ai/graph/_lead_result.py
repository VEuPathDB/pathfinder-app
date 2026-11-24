from __future__ import annotations

from typing import Any

from pydantic_ai import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests

from strategist.ai.graph._lead_capture import LeadRunCapture
from strategist.ai.graph._lead_durable import pending_durable_call
from strategist.ai.graph._lead_turn import pending_approval
from strategist.ai.lead.deleted_steps import ask_about_the_removals
from strategist.ai.lead.lead_memory_tools import ask_about_the_preferences
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import LeadResponse


def absorb_run_result(
    event: AgentRunResultEvent[Any],
    capture: LeadRunCapture,
    deps: LeadDeps,
) -> None:
    run_result = event.result
    response = run_result.response
    if response.finish_reason:
        capture.finish_reason = response.finish_reason
    output = run_result.output
    if isinstance(output, LeadResponse):
        capture.response = output
    elif isinstance(output, DeferredToolRequests):
        messages = list(run_result.all_messages())
        capture.pending_durable_call = pending_durable_call(
            output=output,
            deps=deps,
            messages=messages,
        )
        if capture.pending_durable_call is None:
            capture.pending_approval = pending_approval(
                output=output,
                deps=deps,
                messages=messages,
            )


async def ask_about_what_it_parks(
    event: AgentRunResultEvent[Any], deps: LeadDeps, writer: Any
) -> None:
    """Write the question of each parked removal and preference before its card is drawn."""
    output = event.result.output
    if isinstance(output, DeferredToolRequests):
        await ask_about_the_removals(deps, output, writer)
        ask_about_the_preferences(output, writer)


__all__ = ["absorb_run_result", "ask_about_what_it_parks"]
