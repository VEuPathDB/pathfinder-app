"""The Lead's memory tools: recall what this user's other conversations hold,
and keep what the user asks to be kept."""

from __future__ import annotations

from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.stream_events import recalled_memories_event
from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import memory_tools
from pathfinder.domain.memory import MemoryKind


async def search_memory(
    ctx: RunContext[LeadDeps],
    query: str,
    kind: MemoryKind | None = None,
    top_k: int = 5,
) -> ToolReturn[list[dict[str, object]]]:
    """Recall memories of this user's other conversations. Read-only.

    The briefing names how many of each kind exist; none is read into the turn
    until this call. Recall when the request points at earlier work ("like last
    time", "my usual set") or when what you know of this user would change the
    answer. ``kind`` narrows the search to one kind.
    """
    recalled = await memory_tools.recall(inner_context(ctx), query, kind, top_k)
    fresh = ctx.deps.state.domain.memories_to_show(recalled)
    if fresh:
        emit_chunk(get_stream_writer(), recalled_memories_event(memories=fresh))
    return memory_tools.recalled_return(ctx, query, recalled)


async def remember(
    ctx: RunContext[LeadDeps],
    kind: MemoryKind,
    name: str,
    summary: str,
    content: dict[str, object],
    tags: list[str] | None = None,
) -> ToolReturn[str]:
    """Store one thing the user asked you to keep for future conversations.

    Use it for a stated preference (a default organism, a preferred dataset)
    and for a fact they taught you. One call per thing remembered. Storing a
    preference is the whole answer to that request: do not build a strategy to
    "validate" it.

    It stores a note. A gene set the user asks you to save is created with
    ``save_gene_set``, and ``gene_set_note`` is a note about a set
    that already exists.
    """
    inner = inner_context(ctx)
    return await memory_tools.remember(
        inner,
        kind=kind,
        name=name,
        summary=summary,
        content=content,
        tags=tags,
    )


__all__ = ["remember", "search_memory"]
