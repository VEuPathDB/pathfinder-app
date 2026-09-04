"""Pinned instructions any assistant can render: what it knows about the user,
the notes it kept for this conversation, and the budget its run enforces."""

from __future__ import annotations

from typing import Protocol

from assistant_core.graph.runtime import AssistantDeps
from assistant_core.memory.schemas import MemoryValue
from pydantic_ai.tools import RunContext

from pathfinder.ai.scratchpad.rendering import render_scratchpad_for_phase
from pathfinder.services.conversations.scratchpad_service import ScratchpadNotebook


class CarriesMemories(Protocol):
    """Deps that hold the memories retrieved for the turn.

    The Lead and the sub-agents keep them on containers of their own, so the
    render binds to the field rather than to one of the two types.
    """

    retrieved_memories: list[MemoryValue]


def pinned_user_memories(ctx: RunContext[CarriesMemories]) -> str | None:
    memories = ctx.deps.retrieved_memories
    if not memories:
        return None
    lines = ["## What you know about this user"]
    for m in memories:
        tags_str = f" [{', '.join(m.tags)}]" if m.tags else ""
        lines.append(f"- [{m.kind}] {m.name}{tags_str}: {m.summary}")
    return "\n".join(lines)


async def pinned_scratchpad(ctx: RunContext[AssistantDeps]) -> str | None:
    """Render the conversation's scratchpad index for the phase agent."""
    if ctx.deps.db_session_factory is None or ctx.deps.conversation_id is None:
        return None
    notes, total_count = await ScratchpadNotebook(
        ctx.deps.db_session_factory,
        ctx.deps.conversation_id,
    ).index()
    return render_scratchpad_for_phase(notes, total_count=total_count)


_BUDGET_NOTE = (
    "The run stops the moment either ceiling is reached, mid-task. Spend what "
    "is left on the move that answers the question."
)


def pinned_run_budget(ctx: RunContext[object]) -> str | None:
    """The ceiling this run enforces, against what it has already spent.

    A context that no run backs carries no limits, and a run that limits only
    its request count has nothing the model can steer by.
    """
    limits = ctx.usage_limits
    if limits is None:
        return None
    meters: list[str] = []
    if limits.tool_calls_limit is not None:
        meters.append(f"tools {ctx.usage.tool_calls:,}/{limits.tool_calls_limit:,}")
    if limits.total_tokens_limit is not None:
        meters.append(
            f"tokens {ctx.usage.total_tokens:,}/{limits.total_tokens_limit:,}"
        )
    if not meters:
        return None
    return f"## Run budget\n{' - '.join(meters)}\n{_BUDGET_NOTE}"
