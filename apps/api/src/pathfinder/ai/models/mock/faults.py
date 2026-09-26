"""The wrong calls a fault token inserts into an arc, once per turn."""

from __future__ import annotations

from dataclasses import dataclass, replace

from assistant_core.models.scripted import (
    called_tool_parts,
    current_turn,
    retry_prompt_parts,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

from pathfinder.ai.models.mock import fault_calls
from pathfinder.ai.models.mock.arc import Role


@dataclass(frozen=True)
class Fault:
    """The role a fault plays in, the wrong call it makes there, and how many
    times the turn makes it before the arc goes on."""

    applies_to: Role
    wrong_call: fault_calls.WrongCall
    times: int = 1


# A FRAME tool may be refused three times; the fourth refusal stops the pass.
_UNTIL_THE_PASS_STOPS = 4

FAULTS: dict[str, Fault] = {
    "syntenic-left-off": Fault("frame", fault_calls.syntenic_left_off),
    "repeat-control-test": Fault("verification", fault_calls.repeat_control_test),
    "transcript-count": Fault("lead", fault_calls.transcript_count),
    "all-unclear": Fault("verification", fault_calls.all_unclear),
    "sweep-without-controls": Fault("lead", fault_calls.sweep_without_controls),
    "long-reason": Fault("frame", fault_calls.long_reason, _UNTIL_THE_PASS_STOPS),
    "short-card-reply": Fault("lead", fault_calls.short_card_reply),
    "unlisted-search": Fault("frame", fault_calls.unlisted_search),
    "value-as-term": Fault("frame", fault_calls.value_as_term),
    "off-vocabulary": Fault("frame", fault_calls.off_vocabulary),
    "unbacked-controls": Fault("lead", fault_calls.unbacked_controls),
    "misstated-count": Fault("lead", fault_calls.misstated_count),
    "misnamed-deletion": Fault("lead", fault_calls.misnamed_deletion),
}

# The id prefix that marks a call a fault made, which the arc does not count.
_FAULT_CALL = "fault_"


class UnknownFaultError(LookupError):
    """A message names a fault the registry does not hold."""


def fault_named(name: str) -> Fault:
    if name not in FAULTS:
        msg = f"No mock fault is named {name!r}. Known faults: {sorted(FAULTS)}"
        raise UnknownFaultError(msg)
    return FAULTS[name]


def _answered(messages: list[ModelMessage], wrong: ToolCallPart, times: int) -> bool:
    """Whether this turn already made the wrong call, or had it refused,
    ``times`` times. A call is counted once, however often the run carries it."""
    turn = current_turn(messages)
    refused = {
        p.tool_call_id
        for p in retry_prompt_parts(turn)
        if p.tool_name == wrong.tool_name
    }
    made = {
        p.tool_call_id
        for p in called_tool_parts(turn)
        if p.tool_name == wrong.tool_name and p.args_as_dict() == wrong.args_as_dict()
    }
    return max(len(refused), len(made)) >= times


def fault_call(
    name: str | None,
    role: Role,
    messages: list[ModelMessage],
    intended: ToolCallPart,
) -> ToolCallPart | None:
    """The wrong call this role makes in place of ``intended``, or None once
    the fault has answered."""
    if name is None:
        return None
    fault = fault_named(name)
    if fault.applies_to != role:
        return None
    wrong = fault.wrong_call(messages)(intended)
    if wrong is None or _answered(messages, wrong, fault.times):
        return None
    return replace(wrong, tool_call_id=f"{_FAULT_CALL}{wrong.tool_call_id}")


def made_by_a_fault(part: object) -> bool:
    match part:
        case ToolCallPart(tool_call_id=call_id):
            return call_id.startswith(_FAULT_CALL)
        case _:
            return False


def _answers_a_fault(part: object) -> bool:
    match part:
        case (
            ToolReturnPart(tool_call_id=call_id) | RetryPromptPart(tool_call_id=call_id)
        ):
            return call_id.startswith(_FAULT_CALL)
        case _:
            return False


def without_fault_calls(messages: list[ModelMessage]) -> list[ModelMessage]:
    """The run as the arc reads it: every call a fault made, and the answer or
    refusal it got, is left out."""
    kept: list[ModelMessage] = []
    for message in messages:
        match message:
            case ModelResponse(parts=parts):
                kept.append(
                    replace(message, parts=[p for p in parts if not made_by_a_fault(p)])
                )
            case ModelRequest(parts=parts):
                kept.append(
                    replace(
                        message, parts=[p for p in parts if not _answers_a_fault(p)]
                    )
                )
    return kept
