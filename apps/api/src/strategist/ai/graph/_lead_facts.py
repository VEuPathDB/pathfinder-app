"""The facts part a turn writes once, before the first reply it shows, and
which every reply of the turn is rendered from."""

from __future__ import annotations

from typing import Any

from assistant_core.graph.emit import emit_chunk

from strategist.ai.graph._lead_capture import LeadRunCapture
from strategist.ai.graph._lead_stops import shown_refusal
from strategist.ai.graph.stream_events import facts_event, reply_links_event
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.reply_links import reply_links
from strategist.domain.turn_facts import TurnFacts


def show_the_facts(writer: Any, deps: LeadDeps, capture: LeadRunCapture) -> TurnFacts:
    """Write the turn's facts, unless this turn wrote them or they hold nothing,
    and keep them for the replies of the turn."""
    if capture.facts_shown:
        return capture.facts
    capture.facts_shown = True
    refusal = shown_refusal(capture.run_error) or deps.state.turn_markers.unbound_edit
    capture.facts = turn_facts(deps, refusal=refusal)
    deps.state.domain.record_shown(capture.facts.shown_records())
    if not capture.facts.empty():
        emit_chunk(writer, facts_event(capture.facts))
    show_the_links(writer, deps, capture.facts)
    return capture.facts


def show_the_links(writer: Any, deps: LeadDeps, facts: TurnFacts) -> None:
    links = reply_links(facts, deps.state.turn_markers.retrieved_sources)
    if links.links:
        emit_chunk(writer, reply_links_event(links))
