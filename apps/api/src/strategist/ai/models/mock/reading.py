"""The intent the mock reads a turn's words as, the one its arc declares with
any misreading the turn's fault makes, and the operator answers the arc gives."""

from __future__ import annotations

from veupathdb_mcp.catalog import DecisionsTransport

from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.intent import UserIntent
from strategist.ai.models.mock.consult_arc import card_answered
from strategist.ai.models.mock.directive import ArcDirective
from strategist.ai.models.mock.faults import misread
from strategist.ai.models.mock.registry import arc_named
from strategist.ai.models.mock.turn_arc import (
    earlier_words,
    lead_arc_name,
    standing_directive,
    thread_words,
)


def _arc_name(state: PipelineState) -> tuple[str, ArcDirective]:
    directive = standing_directive(state.user_prompt, earlier_words(state))
    named = lead_arc_name(
        directive, card_answered=card_answered(state), texts=thread_words(state)
    )
    return named, directive


def scripted_intent(state: PipelineState, words: str) -> UserIntent:
    named, directive = _arc_name(state)
    return misread(
        directive.fault, arc_named(named).reading(state, words), state.site_id
    )


def scripted_operators(state: PipelineState) -> DecisionsTransport:
    named, _ = _arc_name(state)
    return arc_named(named).operators


__all__ = ["scripted_intent", "scripted_operators"]
