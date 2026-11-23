"""The tool that clears the conversation's strategy."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._validation_helpers import get_graph
from strategist.ai.tools.standalone.conversation_models import ClearStrategyResult
from strategist.ai.tools.standalone.stream_parts import graph_cleared_chunk
from strategist.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from strategist.services.strategies.sync_state import WDKSyncState


async def clear_strategy(
    ctx: RunContext[AgentDeps],
    graph_id: str | None = None,
    confirm: bool = False,
) -> ToolReturn[ClearStrategyResult]:
    """Clear the current strategy and start fresh.

    This removes all steps and the current strategy. Requires explicit confirmation.

    Args:
        graph_id: Graph ID to clear.
        confirm: Set true to confirm deleting all nodes in the graph.
    """
    session = ctx.deps.strategy_session
    graph = get_graph(session, graph_id)
    if not graph:
        msg = (
            f"NOT_FOUND: No strategy has that id (graph_id={graph_id!r}). "
            "Pass the graph id, the VEuPathDB strategy id, or nothing at all "
            "for the active strategy."
        )
        raise ModelRetry(msg)
    if not confirm:
        msg = (
            "VALIDATION_ERROR: Refusing to clear the strategy without confirmation. "
            f"Re-call clear_strategy with confirm=true (graph_id={graph.id!r})."
        )
        raise ModelRetry(msg)

    graph.steps.clear()
    graph.roots.clear()
    graph.history.clear()
    graph.last_step_id = None
    # Reset WDK sync state.
    session.sync_state = WDKSyncState()
    # Without this the row keeps the old AST and the cleared strategy
    # reappears on the next read.
    await persist_strategy_ast_to_conversation(
        deps=ctx.deps.to_strategy_context(),
        graph=graph,
        sync_result=None,
    )

    return with_summary(
        ClearStrategyResult(
            graph_id=graph.id,
            message="Strategy cleared. Ready to start fresh.",
        ),
        "Strategy cleared",
        ctx=ctx,
        extra=[graph_cleared_chunk(reason="user cleared the strategy")],
    )
