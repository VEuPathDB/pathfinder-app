"""The intent the mock reads a turn's words as: the one its arc declares, with
any misreading the turn's fault makes."""

from __future__ import annotations

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.models.mock.consult_arc import card_answered
from pathfinder.ai.models.mock.faults import misread
from pathfinder.ai.models.mock.registry import arc_named
from pathfinder.ai.models.mock.turn_arc import (
    earlier_words,
    lead_arc_name,
    standing_directive,
    thread_words,
)


def scripted_intent(state: PipelineState, words: str) -> UserIntent:
    directive = standing_directive(state.user_prompt, earlier_words(state))
    named = lead_arc_name(
        directive, card_answered=card_answered(state), texts=thread_words(state)
    )
    return misread(
        directive.fault, arc_named(named).reading(state, words), state.site_id
    )


__all__ = ["scripted_intent"]
