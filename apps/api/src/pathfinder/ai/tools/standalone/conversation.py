"""Standalone conversation tools for pydantic-ai agents.

Provides:
- ``rename_strategy`` -- rename the current strategy
- ``clear_strategy`` -- clear the current strategy and start fresh
"""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._validation_helpers import get_graph
from pathfinder.ai.tools.standalone.conversation_models import (
    ClearStrategyResult,
    RenameStrategyResult,
    _has_strategy,
)
from pathfinder.ai.tools.standalone.stream_parts import (
    graph_cleared_chunk,
    strategy_meta_chunk,
)
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.sync_state import WDKSyncState


async def rename_strategy(
    ctx: RunContext[AgentDeps],
    new_name: str,
    description: str,
    graph_id: str | None = None,
) -> ToolReturn[RenameStrategyResult]:
    """Rename the current strategy.

    Args:
        new_name: New name for the strategy.
        description: Strategy description.
        graph_id: Graph ID to rename.
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
    if not _has_strategy(graph, session):
        msg = (
            "INVALID_STRATEGY: No strategy to rename. "
            "Build at least one step before calling rename_strategy."
        )
        raise ModelRetry(msg)

    old_name = graph.name
    graph.name = new_name
    graph.description = description
    graph.save_history(f"Renamed from '{old_name}' to '{new_name}'")

    return with_summary(
        RenameStrategyResult(
            graph_id=graph.id,
            old_name=old_name,
            new_name=new_name,
            name=new_name,
            record_type=graph.record_type or "",
            description=graph.description,
            plan=graph.to_strategy_ast(sync_state=session.sync_state),
        ),
        f"Renamed to {new_name}",
        ctx=ctx,
        extra=[strategy_meta_chunk(session, graph)],
    )


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
