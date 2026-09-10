"""Persist a strategy graph's AST to its conversation row.

Writes under the thread's strategy lock. A caller that already owns that
lock passes its session on the context, so its read and this write are one
transaction; a caller that does not takes the lock for the write alone.
"""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy.session import StrategyGraph
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.domain.strategy.tree import walk
from veupathdb.errors import VEuPathDBError

from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.write_lock import strategy_write_scope

logger = get_logger(__name__)


async def persist_strategy_ast_to_conversation(
    *,
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    sync_result: SyncResult | None,
) -> None:
    """Write ``conversation_strategies.strategy_ast`` from the current graph.

    Re-fetches the row inside the lock to merge any persisted
    ``wdk_step_ids`` the agent didn't see this turn.

    On a partial WDK push the caller passes ``sync_result=None`` so the
    new ``wdk_strategy_id`` is not written; only the incremental
    ``wdk_step_ids`` land.
    """
    if deps.conversation_id is None:
        return
    sync_state = deps.strategy_session.sync_state
    agent_ast = graph.to_strategy_ast(sync_state=sync_state)
    if agent_ast is None:
        # No steps at all. Several roots is a normal mid-edit state and is
        # carried in ``detached_roots``, not skipped.
        await _clear_persisted_strategy(deps)
        return
    scope = strategy_write_scope(deps)
    if scope is None:
        return
    try:
        async with scope as session:
            repo = ConversationRepository(session)
            current = await repo.get_strategy(deps.conversation_id)
            merged_ast = _merge_agent_ast_into_current(current, agent_ast)
            wdk_strategy_id_to_write = (
                sync_result.wdk_strategy_id
                if sync_result is not None
                else current.wdk_strategy_id
            )
            await repo.update_conversation(
                deps.conversation_id,
                ConversationUpdate(
                    strategy_ast=merged_ast,
                    record_type=merged_ast.record_type or None,
                    wdk_strategy_id=wdk_strategy_id_to_write,
                    wdk_strategy_id_set=sync_result is not None,
                    step_count=_total_step_count(merged_ast),
                ),
            )
    except (VEuPathDBError, OSError, RuntimeError) as exc:
        logger.warning(
            "Failed to persist strategy AST to conversation",
            conversation_id=str(deps.conversation_id),
            error=str(exc),
        )


def _total_step_count(ast: StrategyAst) -> int:
    """Every step the researcher can see, pushed or not yet combined."""
    total = len(walk(ast.root))
    for detached in ast.detached_roots:
        total += len(walk(detached))
    return total


async def _clear_persisted_strategy(deps: StrategyMutationContext) -> None:
    """Blank the built strategy after the last step is deleted."""
    scope = strategy_write_scope(deps)
    if scope is None or deps.conversation_id is None:
        return
    try:
        async with scope as session:
            await ConversationRepository(session).clear_strategy(
                deps.conversation_id,
            )
    except (VEuPathDBError, OSError, RuntimeError) as exc:
        logger.warning(
            "Failed to clear strategy AST on conversation",
            conversation_id=str(deps.conversation_id),
            error=str(exc),
        )


def _merge_agent_ast_into_current(
    current: ConversationStrategyView,
    agent_ast: StrategyAst,
) -> StrategyAst:
    """Write the agent's AST but preserve persisted ``wdk_step_ids`` it lacks.

    The agent owns the graph topology (it just mutated it). The persisted
    ``wdk_step_ids`` may include steps the agent already knows about; the
    union keeps any IDs a concurrent writer landed for steps the agent
    did not push this turn. When persisted state is missing entirely
    (fresh chat), use the agent view as-is.
    """
    persisted_ast = current.strategy_ast
    if not persisted_ast:
        return agent_ast
    persisted = StrategyAst.model_validate(persisted_ast)
    merged_step_ids = dict(persisted.wdk_step_ids or {})
    merged_step_ids.update(agent_ast.wdk_step_ids or {})
    return agent_ast.model_copy(update={"wdk_step_ids": merged_step_ids})
