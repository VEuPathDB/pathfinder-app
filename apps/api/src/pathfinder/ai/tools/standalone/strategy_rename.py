"""The Lead's rename of the conversation's strategy, through the sidebar's rename."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.lead.live_state import read_live_state
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.conversation import NOT_STORED
from pathfinder.ai.tools.standalone.graph_helpers import counted_records
from pathfinder.ai.tools.standalone.stream_parts import strategy_meta_chunk
from pathfinder.services.strategies.naming import rename_strategy_everywhere

NO_STRATEGY = (
    "This conversation holds no strategy to rename. Say so, and offer to "
    "build one first."
)


async def rename_strategy(ctx: RunContext[LeadDeps], name: str) -> ToolReturn[str]:
    """Rename this conversation's strategy.

    Call it when the researcher asks for a new name for the strategy. The
    conversation, the strategy panel and the strategy on VEuPathDB all take the
    new name at once; there is no card. Pass the name the user gave, word for
    word. A rename changes no step, so the turn reports ``strategy_changed``
    false. The answer states the name the store kept and the count the
    strategy returns now.

    Args:
        name: The new name.
    """
    runtime = ctx.deps.runtime
    session = runtime.strategy_session
    graph = session.get_graph(None)
    if graph is None or not graph.steps:
        raise ModelRetry(NO_STRATEGY)
    stored = await rename_strategy_everywhere(
        ctx.deps.state.conversation_id,
        name,
        session_factory=runtime.db_session_factory,
    )
    if stored is None:
        raise ModelRetry(NOT_STORED)
    graph.name = stored
    live = await read_live_state(session, runtime.site_id)
    meta = [strategy_meta_chunk(session, graph)]
    renamed = f"Renamed the strategy to {graph.name}."
    if live.root_count is None:
        return with_summary(
            f"{renamed} The site gives no count for it now.",
            f"{graph.name} - count not available",
            ctx=ctx,
            status="warn",
            extra=meta,
        )
    counted = counted_records(live.root_count, graph.record_type)
    return with_summary(
        f"{renamed} It returns {counted}.",
        f"{graph.name} - {counted}",
        ctx=ctx,
        extra=meta,
    )
