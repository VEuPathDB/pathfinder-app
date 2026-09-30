"""The Lead's reads of the strategy as it stands and of its own ledger."""

from __future__ import annotations

from typing import Literal

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.live_state import LiveStrategyState, read_live_state
from pathfinder.ai.lead.sub_agent_tools import LeadDeps

LedgerSectionName = Literal["frame", "build", "verification"]


async def get_live_strategy_state(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[LiveStrategyState]:
    """Read the strategy as it exists RIGHT NOW, bypassing the Ledger's cache.

    The Ledger's build counts describe the last build this conversation ran.
    The user can change the strategy between turns (graph editor, VEuPathDB
    web UI), which leaves those counts wrong. Call this before describing the
    strategy as it stands, and always when the Ledger shows a STALE marker or
    the user asks what the strategy does "now".

    Every count comes from the site, and the facts beside the reply show it.
    An ``estimatedSize`` or ``rootCount`` of null is UNKNOWN, never zero.
    Describe a step from its ``parameters``, which are the values stored on
    it; its name can still describe the value it was built with.
    """
    live = await read_live_state(
        ctx.deps.runtime.strategy_session,
        ctx.deps.runtime.site_id,
    )
    if not live.step_count:
        return with_summary(live, "No strategy yet", ctx=ctx, status="empty")
    genes = live.root_count
    if genes is None:
        return with_summary(
            live,
            f"{live.step_count} steps, count not available",
            ctx=ctx,
            status="warn",
        )
    return with_summary(
        live,
        f"{live.step_count} steps, {genes:,} genes",
        ctx=ctx,
        status="ok" if genes else "empty",
    )


def read_ledger_section(
    ctx: RunContext[LeadDeps],
    section: LedgerSectionName,
) -> ToolReturn[str]:
    """Return the full detail of one Ledger section.

    The pinned summary already shows counts and derived booleans; use
    this when you need step-level detail (failed step IDs, open slot
    questions, fit-report rationales) before deciding the next move.
    """
    ledger = derive_ledger(ctx.deps.state, ctx.deps.intent)
    return with_summary(
        ledger.render_section(section),
        f"Read {section}",
        ctx=ctx,
    )
