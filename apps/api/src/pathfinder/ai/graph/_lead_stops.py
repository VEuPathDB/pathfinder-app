"""Why a Lead run ended on the guard, and the reply that says so."""

from __future__ import annotations

from typing import Any

from assistant_core.capabilities.repetition_guard import (
    CALL_CAP_MARKER,
    BlockRule,
    ToolRepetitionGuard,
)
from pydantic_ai.messages import AgentStreamEvent, FunctionToolResultEvent
from pydantic_ai.run import AgentRunResultEvent

from pathfinder.ai.graph._lead_capture import GuardStop, _LeadRunCapture
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.turn_contract import LeadResponse


def guard_stopped_on(
    event: AgentStreamEvent | AgentRunResultEvent[Any],
    guard: ToolRepetitionGuard,
) -> bool:
    """True for the result of the call whose refusal ends the run."""
    return (
        isinstance(event, FunctionToolResultEvent)
        and event.tool_call_id == guard.stopped_call_id
    )


def guard_stop_of(event: FunctionToolResultEvent) -> GuardStop:
    """The rule the refusal names: the runtime marks a budget stop in its text."""
    text = str(event.part.content)
    rule: BlockRule = "call_cap" if CALL_CAP_MARKER in text else "identical_arguments"
    return GuardStop(tool_name=event.part.tool_name or "", rule=rule)


def loop_stop_prose(stop: GuardStop | None) -> str:
    """What the user reads when the guard ended the run."""
    if stop is not None and stop.rule == "call_cap":
        return (
            f"I stopped this turn: I read {stop.tool_name} past its budget for one "
            "turn without settling the answer. Ask me to continue and I will "
            "answer from what it returned, or narrow the question."
        )
    return (
        "I stopped this turn: I was repeating the same lookup and making "
        "no progress. Tell me what to try instead and I will carry on."
    )


def stop_response(prose: str, *, changed: bool) -> LeadResponse:
    """The reply the runtime writes when a turn ends without one."""
    return LeadResponse(prose=prose, next_state="await_user", strategy_changed=changed)


def absorb_loop_stop(
    state: PipelineState,
    capture: _LeadRunCapture,
    guard: ToolRepetitionGuard,
) -> None:
    """Say why the turn ended when the guard stopped the Lead's own run."""
    if not guard.stopped_call_id or capture.response is not None:
        return
    capture.response = stop_response(
        loop_stop_prose(capture.guard_stop),
        changed=state.turn_markers.changed_strategy,
    )
