"""How a Lead run's chunks reach the thread: a sub-agent's own calls are
suppressed, and the held cards are written after the facts they stand beside."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from assistant_core.graph.emit import emit_chunk
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    ErrorChunk,
    ToolApprovalRequestChunk,
    ToolInputAvailableChunk,
    ToolInputDeltaChunk,
    ToolInputErrorChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
    ToolOutputDeniedChunk,
    ToolOutputErrorChunk,
)

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.graph._lead_events import is_suppressed_sub_agent_chunk
from pathfinder.ai.graph._lead_facts import show_the_facts
from pathfinder.ai.lead.sub_agent_tools import LeadDeps

_CALL_CHUNKS = (
    ToolInputStartChunk,
    ToolInputDeltaChunk,
    ToolInputAvailableChunk,
    ToolInputErrorChunk,
    ToolApprovalRequestChunk,
    ToolOutputAvailableChunk,
    ToolOutputErrorChunk,
    ToolOutputDeniedChunk,
)


async def without_calls_of(
    earlier_calls: frozenset[str], chunks: AsyncIterator[BaseChunk]
) -> AsyncIterator[BaseChunk]:
    async for chunk in chunks:
        if isinstance(chunk, _CALL_CHUNKS) and chunk.tool_call_id in earlier_calls:
            continue
        yield chunk


def _emit_unless_suppressed(
    writer: Any,
    chunk: BaseChunk,
    sub_agent_tool_calls: dict[str, str],
    capture: _LeadRunCapture,
) -> None:
    """Write one chunk, unless a sub-agent already renders that call itself.

    The error chunk that ends a run is kept, so the turn's reply can name it.
    """
    if isinstance(chunk, ErrorChunk):
        capture.run_error = chunk.error_text
    if is_suppressed_sub_agent_chunk(chunk, sub_agent_tool_calls):
        return
    emit_chunk(writer, chunk)


def emit_each(
    writer: Any,
    chunks: list[BaseChunk],
    sub_agent_tool_calls: dict[str, str],
    capture: _LeadRunCapture,
) -> None:
    for chunk in chunks:
        _emit_unless_suppressed(writer, chunk, sub_agent_tool_calls, capture)


def release_the_cards(
    writer: Any,
    hold: CardHold,
    deps: LeadDeps,
    capture: _LeadRunCapture,
    sub_agent_tool_calls: dict[str, str],
) -> None:
    """Write the held cards, after the facts their replies stand beside and are
    rendered from."""
    if not hold.holds_a_card():
        return
    facts = show_the_facts(writer, deps, capture)
    emit_each(writer, hold.release(facts), sub_agent_tool_calls, capture)
