"""The arc a turn plays, for the reading of its words and for each role's script
alike."""

from __future__ import annotations

from collections.abc import Sequence

from strategist.ai.conversation.gene_list_marker import parse_gene_list_marker
from strategist.ai.graph.state import PipelineState
from strategist.ai.models.mock.directive import ECHO, ArcDirective, directive_of


def standing_directive(said: str, earlier: Sequence[str]) -> ArcDirective:
    directive = directive_of(said)
    if directive.arc != ECHO:
        return directive
    named = (directive_of(text) for text in reversed(earlier))
    return next((found for found in named if found.arc != ECHO), directive)


def lead_arc_name(directive: ArcDirective, *, card_answered: bool, texts: str) -> str:
    if card_answered:
        return "consult"
    if directive.arc == ECHO and parse_gene_list_marker(texts) is not None:
        return "attachment"
    return directive.arc


def earlier_words(state: PipelineState) -> list[str]:
    domain = state.domain
    said = [exchange.said for exchange in domain.exchanges]
    return [domain.original_request, *domain.request_messages, *said]


def thread_words(state: PipelineState) -> str:
    return "\n".join([*earlier_words(state), state.user_prompt])
