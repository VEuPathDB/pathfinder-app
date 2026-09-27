"""The refusals the classification gate holds an intent to, read from the turn."""

from __future__ import annotations

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import (
    IntentClassification,
    UserIntent,
    nothing_to_answer_message,
    unstated_control_ids,
    unstated_controls_message,
    unstated_operator_refusal,
)


def _answers_nothing(state: PipelineState, intent: UserIntent) -> bool:
    """Whether the intent answers a question on a turn that holds none."""
    return (
        intent.classification is IntentClassification.CLARIFICATION_RESPONSE
        and not state.turn_markers.questions_at_arrival
        and state.pending_approval is None
    )


def classification_refusal(state: PipelineState, intent: UserIntent) -> str | None:
    """Why this intent does not describe the turn's message, or None."""
    message = state.user_prompt
    operator = unstated_operator_refusal(intent, message)
    if operator is not None:
        return operator
    if _answers_nothing(state, intent):
        return nothing_to_answer_message()
    named = intent.named_controls
    unstated = [] if named is None else unstated_control_ids(named, message)
    return unstated_controls_message(unstated) if unstated else None
