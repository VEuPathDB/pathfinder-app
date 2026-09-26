"""The Lead arcs that clear or rename a strategy, offer a change on a card, or
tune the strategy's root."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.lead_flow import (
    BUILD,
    build_classification,
    build_journey,
    written_tail,
)
from pathfinder.ai.models.mock.message_words import named_after, turn_controls
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    built_count_sentence,
    built_root_wdk_step_id,
    control_set_id,
    last_return,
    live_root_wdk_step_id,
    live_step_id,
    text_return,
)
from pathfinder.ai.models.mock.strategy_specs import TM_DOMAINS

_CLEARED_PROSE = "The current strategy has been cleared."
_UNCHANGED_PROSE = "The strategy is unchanged."
_PROPOSED_PROSE = "The change you accepted is applied to the strategy."
_RENAME = "rename_strategy"
_LIVE = "get_live_strategy_state"
_RENAMED_NAME = "Mock strategy"
_NOT_RENAMED_PROSE = "Nothing was renamed: this conversation holds no strategy yet."
_SWEEP_BUDGET = 6
_SWEEP_CONTROLS = "Controls the sweep scores against"
_SWEEP_REPLY = "[mock] I will sweep the step's settings against your controls."
_SWEEP_PROSE = (
    "The sweep is running. I will report the winning setting and its score "
    "when it reports."
)
_DELETE_REPLY = (
    "[mock] Removing the transmembrane domains step takes the intersection above "
    "it with it; the signal peptide step stays."
)
DELETED_PROSE = (
    "Removed the transmembrane domains step and the intersection above it. The "
    "signal peptide step is the strategy now."
)
_NO_STEP_PROSE = "The strategy holds no transmembrane domains step to remove."
_PROPOSAL = {
    "question": "Add one more search to make this strategy more specific?",
    "proposedChanges": ["Keep only the genes another search of the site returns"],
    "reply": "[mock] One change would make this strategy more specific.",
}


class _Cleared(ToolAnswer):
    graph_id: str


class _Edited(ToolAnswer):
    diff: dict[str, object]


def clear(messages: list[ModelMessage]) -> list[ToolCallPart]:
    cleared = last_return(messages, "clear_strategy", _Cleared) is not None
    return [
        classify("edit_strategy"),
        scripted_call(
            "clear_strategy",
            {
                "reply": "[mock] Clearing removes every step of this strategy.",
                "confirm": True,
            },
        ),
        lead_final(_CLEARED_PROSE, "await_user", strategy_changed=True)
        if cleared
        else lead_final(_UNCHANGED_PROSE, "await_user"),
    ]


def proposal(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Offer one change on a card; a yes runs it as an edit."""
    applied = last_return(messages, "propose_changes", _Edited) is not None
    return [
        classify("follow_up_question"),
        scripted_call("propose_changes", _PROPOSAL),
        lead_final(_PROPOSED_PROSE, "await_user", strategy_changed=True)
        if applied
        else lead_final(_UNCHANGED_PROSE, "await_user"),
    ]


def rename(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Rename the strategy to the words after "to", and answer with the tool's line."""
    answered = text_return(messages, _RENAME)
    return [
        classify("edit_strategy"),
        scripted_call(_RENAME, {"name": named_after("to") or _RENAMED_NAME}),
        lead_final(_NOT_RENAMED_PROSE if answered is None else answered, "await_user"),
    ]


def _saved_controls() -> ToolCallPart:
    positives, negatives = turn_controls()
    return scripted_call(
        "build_control_set",
        {
            "name": _SWEEP_CONTROLS,
            "positive_ids": positives,
            "negative_ids": negatives,
        },
    )


def _swept(wdk_step_id: int | None, messages: list[ModelMessage]) -> ToolCallPart:
    return scripted_call(
        "optimize_search_parameters",
        {
            "reply": _SWEEP_REPLY,
            "wdk_step_id": wdk_step_id,
            "control_set_id": control_set_id(messages),
            "budget": _SWEEP_BUDGET,
        },
    )


def sweep(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read the live strategy and tune the root it names; a thread with no
    root saves the controls, then builds, verifies and tunes one, so the build's
    answer is still whole when the reply names what it added."""
    read = [classify(build_classification(messages)), scripted_call(_LIVE, {})]
    root = live_root_wdk_step_id(messages)
    if root is not None:
        swept = _swept(root, messages)
        return [*read, _saved_controls(), swept, lead_final(_SWEEP_PROSE, "await_user")]
    journey = build_journey(messages)
    if journey[-2].tool_name == BUILD:
        return [*read, *journey[1:]]
    built = built_root_wdk_step_id(messages)
    return [
        *read,
        _saved_controls(),
        *journey[1:-2],
        _swept(built, messages),
        lead_final(
            f"{_SWEEP_PROSE}{written_tail(messages, built_count_sentence(messages))}",
            "await_user",
            strategy_changed=True,
        ),
    ]


def delete_card(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Read the live strategy, remove its transmembrane step on the delete card,
    and name the step the card removed."""
    head = [classify("edit_strategy"), scripted_call("get_live_strategy_state", {})]
    step_id = live_step_id(messages, TM_DOMAINS)
    if step_id is None:
        return [*head, lead_final(_NO_STEP_PROSE, "await_user")]
    return [
        *head,
        scripted_call("delete_step", {"step_id": step_id, "reply": _DELETE_REPLY}),
        lead_final(DELETED_PROSE, "await_user", strategy_changed=True),
    ]
