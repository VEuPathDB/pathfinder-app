"""Why a Lead run ended on the guard, and the reply that says so."""

from __future__ import annotations

import re
from typing import Any

from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from pydantic_ai.messages import AgentStreamEvent, FunctionToolResultEvent
from pydantic_ai.run import AgentRunResultEvent

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph._lead_capture import GuardStop, _LeadRunCapture
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import UnansweredStage
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.provider_keys import PROVIDER_NAMES
from pathfinder.platform.model_catalog import get_model_entry
from pathfinder.platform.model_keys import turn_refusals


def guard_stop_of(
    event: AgentStreamEvent | AgentRunResultEvent[Any],
    guard: ToolRepetitionGuard,
) -> GuardStop | None:
    """The stop when this event is the result of the call that ends the run."""
    rule = guard.stopped_rule
    match event:
        case FunctionToolResultEvent() if (
            rule is not None and event.tool_call_id == guard.stopped_call_id
        ):
            return GuardStop(tool_name=event.part.tool_name or "", rule=rule)
        case _:
            return None


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


# A link's query can carry a credential, so the refusal is shown without it.
_URL_QUERY = re.compile(r"(\S*://[^\s?]*)\?\S*")
_SHOWN_BESIDE = "what it answered is shown beside this reply"


def shown_refusal(error: str | None) -> str:
    """The refusal that ended the run, whole, with each link's query left out."""
    return _URL_QUERY.sub(r"\1", (error or "").strip())


# What a stopped turn asks for next. A turn whose change landed keeps that
# change, so it asks for the check and never for the message again.
_SEND_AGAIN = "Send the message again and I will start over from it."
_CHECK_THE_CHANGE = (
    "The change shown beside this reply landed and was not checked. Ask me to "
    "check it and I will go on from there."
)
_AFTER_SETTINGS: dict[bool, str] = {
    False: "or send the message again and I will start over from it.",
    True: "then ask me to check the change shown beside this reply, which landed.",
}
_AFTER_KEYS: dict[bool, str] = {
    False: "then send the message again.",
    True: "then ask me to check the change shown beside this reply, which landed.",
}
# The name the model settings show for each stage a researcher can set.
_STAGE_LABELS: dict[PhaseRole, str] = {
    "lead": "Assistant",
    "frame": "Planning",
    "execution": "Building",
    "verification": "Checking",
}


def _stage_that_did_not_answer(
    capture: _LeadRunCapture,
    unanswered: UnansweredStage | None,
) -> UnansweredStage | None:
    """The stage of this turn whose model produced nothing, if there was one.

    A dispatch records its own stage. The Lead's stage is left for the run that
    reached no dispatch at all.
    """
    if unanswered is not None:
        return unanswered
    if capture.model_answered:
        return None
    return UnansweredStage(role="lead", model_id=capture.lead_model)


def _what_to_do_next(
    capture: _LeadRunCapture,
    unanswered: UnansweredStage | None,
    *,
    changed: bool,
) -> str:
    """The action the reply offers, which names a model that never answered.

    The catalog holds every model a researcher can pick, so an id outside it is
    no choice to point at.
    """
    again = _CHECK_THE_CHANGE if changed else _SEND_AGAIN
    stage = _stage_that_did_not_answer(capture, unanswered)
    if stage is None:
        return again
    entry = get_model_entry(stage.model_id)
    if entry is None:
        return again
    return (
        f"The {_STAGE_LABELS[stage.role]} stage of this turn runs {entry.name}, "
        f"and it did not answer. Choose a different model for that stage in "
        f"Settings, {_AFTER_SETTINGS[changed]}"
    )


def _refused_key_prose(*, changed: bool) -> str | None:
    """The reply for a turn a provider stopped by refusing the researcher's key.

    The key is the thing to change, so the reply names it and no model.
    """
    names = [PROVIDER_NAMES[provider] for provider in turn_refusals()]
    if not names:
        return None
    refused = " and ".join(names)
    keys = " and ".join(f"your {name} key" for name in names)
    return (
        f"I stopped this turn: {refused} refused the key you added, so nothing "
        f"more ran on it. Replace or remove {keys} in Settings, under Provider "
        f"keys, {_AFTER_KEYS[changed]}"
    )


def fallback_prose(
    capture: _LeadRunCapture,
    unanswered: UnansweredStage | None,
    *,
    changed: bool,
) -> str:
    """What the user reads when the run ended with no reply of its own."""
    refused = _refused_key_prose(changed=changed)
    if capture.run_error and refused is not None:
        return refused
    if capture.run_error:
        return (
            f"I stopped this turn on an error I could not recover from; "
            f"{_SHOWN_BESIDE}. {_what_to_do_next(capture, unanswered, changed=changed)}"
        )
    if changed:
        return _CHECK_THE_CHANGE
    return (
        "I couldn't produce a response for this turn. Please rephrase or provide "
        "more context and I'll try again."
    )


def final_reply(
    capture: _LeadRunCapture,
    unanswered: UnansweredStage | None,
    *,
    changed: bool,
) -> LeadResponse | None:
    """The turn's reply: the run's own, or one that says why there is none.

    A run that answered keeps its answer, whatever chunks it wrote on the way.
    A turn parked on a call the user or a worker answers has no reply yet, and
    a declined proposal keeps the reply the card was offered under.
    """
    if capture.response is not None:
        return capture.response
    if capture.pending_approval is not None or capture.pending_durable_call is not None:
        return None
    if capture.offer_declined:
        return None
    return stop_response(
        fallback_prose(capture, unanswered, changed=changed), changed=changed
    )
