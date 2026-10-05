"""Pinned instructions any assistant can render: what it knows about the user,
the notes it kept for this conversation, and the budget its run enforces."""

from __future__ import annotations

from typing import Protocol

from assistant_core.graph.runtime import AssistantDeps
from assistant_core.memory.schemas import MemoryValue
from assistant_core.scratchpad.notebook import ScratchpadNotebook
from assistant_core.scratchpad.rendering import render_scratchpad
from pydantic_ai.tools import RunContext

from pathfinder.ai.agents.scratchpad_guidance import PATHFINDER_SCRATCHPAD_GUIDANCE
from pathfinder.domain.exchanges import Exchange, exchanges_section


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


class CarriesExchanges(Protocol):
    """Deps that hold the conversation's last exchanges."""

    exchanges: list[Exchange]


def pinned_conversation_so_far(ctx: RunContext[CarriesExchanges]) -> str | None:
    return exchanges_section(ctx.deps.exchanges)


async def pinned_scratchpad(ctx: RunContext[AssistantDeps]) -> str | None:
    """Render the conversation's scratchpad index for the phase agent."""
    if ctx.deps.db_session_factory is None or ctx.deps.conversation_id is None:
        return None
    notes, total_count = await ScratchpadNotebook(
        ctx.deps.db_session_factory,
        ctx.deps.conversation_id,
    ).index()
    return render_scratchpad(
        notes,
        total_count=total_count,
        guidance=PATHFINDER_SCRATCHPAD_GUIDANCE,
    )


_BUDGET_NOTE = (
    "Count the calls you have made and spend what is left on the move that "
    "answers the question."
)


def pinned_run_budget(ctx: RunContext[object]) -> str | None:
    """The ceilings this run enforces, in text every request of the run shares.

    A context that no run backs carries no limits, and a run that limits only
    its request count has nothing the model can steer by.
    """
    limits = ctx.usage_limits
    if limits is None:
        return None
    ceilings: list[str] = []
    if limits.tool_calls_limit is not None:
        ceilings.append(f"{limits.tool_calls_limit:,} tool calls")
    if limits.total_tokens_limit is not None:
        ceilings.append(f"{limits.total_tokens_limit:,} tokens")
    if not ceilings:
        return None
    first = ", whichever comes first" if len(ceilings) > 1 else ""
    reach = " or ".join(ceilings) + first
    return f"## Run budget\nThis run stops at {reach}, mid-task. {_BUDGET_NOTE}"
