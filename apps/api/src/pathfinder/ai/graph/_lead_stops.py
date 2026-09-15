"""Why a Lead run ended on the guard, and the reply that says so."""

from __future__ import annotations

import re
from typing import Any

from assistant_core.capabilities.repetition_guard import (
    CALL_CAP_MARKER,
    BlockRule,
    ToolRepetitionGuard,
)
from pydantic import BaseModel, ConfigDict, model_validator
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


# One clause is what the reader needs; the rest of an error text is the
# provider's payload.
MAX_FAILURE_CLAUSE_CHARS = 120

_PROVIDER_ERROR = re.compile(r"^status_code:\s*(?P<status>\d{3})\b")
# A payload starts at its first bracket and runs to the end of the text.
_PAYLOAD = re.compile(r"[{\[].*", re.DOTALL)
_URL = re.compile(r"\S*://\S*")
_UNNAMED_FAILURE = "the run failed"


class _FailureText(BaseModel):
    """An error text, read as the one clause the user needs."""

    model_config = ConfigDict(frozen=True)

    status: int | None = None
    clause: str = ""

    @model_validator(mode="before")
    @classmethod
    def _read_the_error_text(cls, value: object) -> object:
        match value:
            case str() as text:
                found = _PROVIDER_ERROR.match(text.strip())
                if found is not None:
                    return {"status": int(found["status"])}
                return {"clause": _one_clause(text)}
            case _:
                return value

    def sentence(self) -> str:
        """What the reply says happened."""
        if self.status is not None:
            return f"the model provider answered {self.status}"
        return self.clause or _UNNAMED_FAILURE


def _one_clause(text: str) -> str:
    """The first line of an error, without its payload, its urls or its length."""
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    plain = _URL.sub("", _PAYLOAD.sub("", first))
    clause = " ".join(plain.split())
    if len(clause) <= MAX_FAILURE_CLAUSE_CHARS:
        return clause
    return clause[:MAX_FAILURE_CLAUSE_CHARS].rsplit(" ", 1)[0]


def fallback_prose(capture: _LeadRunCapture) -> str:
    """What the user reads when the run ended with no reply of its own."""
    if capture.run_error:
        return (
            "I stopped this turn on an error I could not recover from: "
            f"{_FailureText.model_validate(capture.run_error).sentence()}. "
            "Send the message again and I will start over from it."
        )
    return (
        "I couldn't produce a response for this turn. Please rephrase or provide "
        "more context and I'll try again."
    )


def final_reply(capture: _LeadRunCapture, *, changed: bool) -> LeadResponse | None:
    """The turn's reply: the run's own, or one that says why there is none.

    A run that answered keeps its answer, whatever chunks it wrote on the way.
    A turn parked on a call the user or a worker answers has no reply yet.
    """
    if capture.response is not None:
        return capture.response
    if capture.pending_approval is not None or capture.pending_durable_call is not None:
        return None
    return stop_response(fallback_prose(capture), changed=changed)
