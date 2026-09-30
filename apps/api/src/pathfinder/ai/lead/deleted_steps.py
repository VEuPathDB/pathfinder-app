"""The step a delete removes, as its approval card asks and its reply names it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.tool_summary import count_noun, summary_chunks
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai.tools import DeferredToolRequests
from veupathdb.domain.strategy import StrategyStep

from pathfinder.ai.graph.stream_events import delete_cascade_event
from pathfinder.ai.graph.turn_records import NamedStep
from pathfinder.ai.lead._delete_rules import delete_cascade
from pathfinder.ai.lead.live_state import LiveStrategyState, read_live_state
from pathfinder.ai.lead.sub_agent_tools import LeadDeps

DELETE_TOOL = "delete_step"
REPLACE_TOOL = "replace_subtree"


class _DeleteArgs(CamelModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str


def named_step(step: StrategyStep) -> NamedStep:
    """The step as a reply can name it."""
    return NamedStep(title=step.display_label, search_name=step.search_name)


def _named(live: LiveStrategyState, step_id: str) -> str | None:
    """The step by its title, search and count, as a card names it."""
    step = next((s for s in live.steps if s.step_id == step_id), None)
    if step is None:
        return None
    count = (
        "count not available"
        if step.estimated_size is None
        else count_noun(step.estimated_size, "gene")
    )
    facts = [fact for fact in (step.search_name, count) if fact]
    return f"'{step.display_name}' ({', '.join(facts)})"


def delete_question(live: LiveStrategyState, step_id: str) -> str | None:
    """The delete card's question: the step by its title, search and count."""
    named = _named(live, step_id)
    return None if named is None else f"Delete step {named}?"


def _also_removed(
    live: LiveStrategyState, step_id: str, removed: Sequence[str]
) -> list[str]:
    """Each other step the delete removes, as the card names it."""
    return [
        shown
        for other in removed
        if other != step_id and (shown := _named(live, other)) is not None
    ]


def _removal_card(
    deps: LeadDeps,
    live: LiveStrategyState,
    call: tuple[str, str, dict[str, Any]],
) -> tuple[str | None, list[str]]:
    """The card's question and the other steps it removes."""
    tool_call_id, tool_name, args = call
    step_id = _DeleteArgs.model_validate(args).step_id
    if tool_name == DELETE_TOOL:
        session = deps.runtime.strategy_session
        graph = session.get_graph(None)
        removed = (
            []
            if graph is None or step_id not in graph.steps
            else delete_cascade(graph, session.sync_state, step_id)
        )
        deps.state.turn_markers.delete_cards[tool_call_id] = removed
        return delete_question(live, step_id), _also_removed(live, step_id, removed)
    named = _named(live, step_id)
    question = (
        None if named is None else f"Replace step {named} and the steps under it?"
    )
    return question, []


async def ask_about_the_removals(
    deps: LeadDeps, requests: DeferredToolRequests, writer: Any
) -> None:
    """Write each parked removal's question as the first line of its call.

    The Lead's own deletes are asked, and so are the removals a pass it
    dispatched stopped at. A delete's card lists every other step it removes,
    read from the graph before the card, never from the reply.
    """
    parked = [
        (call.tool_call_id, call.tool_name, call.args_as_dict())
        for call in requests.approvals
    ] + [
        (call.tool_call_id, call.tool_name, call.args)
        for pending in deps.pending_sub_agent_approvals.values()
        for call in pending.approvals
    ]
    removals = [p for p in parked if p[1] in (DELETE_TOOL, REPLACE_TOOL)]
    if not removals:
        return
    runtime = deps.runtime
    live = await read_live_state(runtime.strategy_session, runtime.site_id)
    for call in removals:
        question, removes = _removal_card(deps, live, call)
        if question is None:
            continue
        for chunk in summary_chunks(call[0], question):
            emit_chunk(writer, chunk)
        if removes:
            emit_chunk(
                writer, delete_cascade_event(tool_call_id=call[0], removes=removes)
            )


__all__ = [
    "DELETE_TOOL",
    "ask_about_the_removals",
    "delete_question",
    "named_step",
]
