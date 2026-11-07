from __future__ import annotations

from typing import Final
from uuid import UUID

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import ApprovalRequired, ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._frame_saved import saved_strategy_listing
from pathfinder.ai.tools.standalone.saved_strategies import SavedStrategiesResult
from pathfinder.services.conversations.thread_reading import (
    ThreadListing,
    ThreadReading,
    other_threads,
    read_thread,
    standing_leave,
)
from pathfinder.services.evidence.gene_sets import get_gene_set

ASK_TOOL: Final = "ask_to_read_the_account"
_GENES_READ = 500
_NO_LEAVE = (
    "Reading the researcher's saved strategies, other conversations or gene sets "
    "needs their leave. Call ask_to_read_the_account first, naming what you want to "
    "read and why."
)


class GeneSetReading(CamelModel):
    name: str
    site_id: str
    gene_count: int
    gene_ids: list[str]


async def _has_leave(ctx: RunContext[LeadDeps]) -> None:
    state = ctx.deps.state
    if state.turn_markers.account_reads_allowed:
        return
    if await standing_leave(state.conversation_id, state.user_id):
        return
    raise ModelRetry(_NO_LEAVE)


async def ask_to_read_the_account(ctx: RunContext[LeadDeps], what: str) -> str:
    """Ask the researcher's leave to read their saved strategies, their other
    PathFinder conversations or the genes of their gene sets.

    A card shows ``what`` and asks; the researcher allows it or not. Ask only when
    reading them would change your answer. An allowed ask lets this turn's reads
    run.

    Args:
        what: What you want to read and why, in the researcher's terms.
    """
    del what
    if not ctx.tool_call_approved:
        raise ApprovalRequired
    ctx.deps.state.turn_markers.account_reads_allowed = True
    return "The researcher allowed it. Read what you asked for."


async def read_saved_strategies(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[SavedStrategiesResult]:
    """The strategies the researcher saved on this site. Needs their leave."""
    await _has_leave(ctx)
    entries = await saved_strategy_listing(inner_context(ctx))
    return with_summary(
        SavedStrategiesResult(saved_strategies=entries),
        count_noun(len(entries), "saved strategy"),
        ctx=ctx,
    )


async def list_my_threads(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[list[ThreadListing]]:
    """The researcher's other PathFinder conversations, most recent first. Needs
    their leave."""
    await _has_leave(ctx)
    state = ctx.deps.state
    threads = await other_threads(state.user_id, but=state.conversation_id)
    return with_summary(threads, count_noun(len(threads), "conversation"), ctx=ctx)


async def read_my_thread(
    ctx: RunContext[LeadDeps], conversation_id: UUID
) -> ToolReturn[ThreadReading]:
    """The requests and replies of one of the researcher's other conversations,
    the latest 20. Needs their leave."""
    await _has_leave(ctx)
    read = await read_thread(ctx.deps.state.user_id, conversation_id)
    return with_summary(read, f"read {read.name}", ctx=ctx)


async def read_gene_set(
    ctx: RunContext[LeadDeps], gene_set_id: str
) -> ToolReturn[GeneSetReading]:
    """The genes of one of the researcher's gene sets, the first 500. Needs their
    leave. ``list_gene_sets`` names the sets and their ids."""
    await _has_leave(ctx)
    gene_set = await get_gene_set(gene_set_id, user_id=ctx.deps.state.user_id)
    if gene_set is None:
        msg = f"The researcher holds no gene set {gene_set_id}; list_gene_sets names theirs."
        raise ModelRetry(msg)
    read = GeneSetReading(
        name=gene_set.name,
        site_id=gene_set.site_id,
        gene_count=len(gene_set.gene_ids),
        gene_ids=gene_set.gene_ids[:_GENES_READ],
    )
    return with_summary(read, f"{read.name}: {read.gene_count} genes", ctx=ctx)


__all__ = [
    "ASK_TOOL",
    "GeneSetReading",
    "ask_to_read_the_account",
    "list_my_threads",
    "read_gene_set",
    "read_my_thread",
    "read_saved_strategies",
]
