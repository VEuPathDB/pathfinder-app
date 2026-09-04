"""Helpers for hydrating in-memory strategy session context for agents."""

from assistant_core.persistence.models import Conversation
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from pydantic import ValidationError

from pathfinder.domain.conversation import DEFAULT_STREAM_NAME
from pathfinder.domain.strategy.graph_model import flatten_tree
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.strategy_ast import (
    PersistedStrategyGraph,
    StrategyAst,
)
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.platform.errors import StrategyAstCorruptError
from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


_MAX_REASONS = 5


def _stored_ast(conversation_id: str, raw: JSONObject) -> StrategyAst | None:
    """Parse the stored AST. An empty row is a thread with no strategy."""
    if not raw:
        return None
    try:
        return StrategyAst.model_validate(raw)
    except ValidationError as exc:
        reasons = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:_MAX_REASONS]
        )
        raise StrategyAstCorruptError(conversation_id, reasons) from exc


def persisted_graph(
    conversation: Conversation,
    strategy: ConversationStrategyView,
) -> PersistedStrategyGraph:
    """The thread's stored graph; a thread with no strategy carries no AST."""
    conversation_id = str(conversation.id)
    return PersistedStrategyGraph(
        id=conversation_id,
        name=conversation.name,
        strategy_ast=_stored_ast(conversation_id, strategy.strategy_ast),
        wdk_strategy_id=strategy.wdk_strategy_id,
    )


def _restore_wdk_state(
    persisted: PersistedStrategyGraph, graph: StrategyGraph
) -> WDKSyncState:
    """Restore WDK state from persisted strategy graph payload."""
    sync_state = WDKSyncState()

    if persisted.wdk_strategy_id is not None:
        sync_state.wdk_strategy_id = persisted.wdk_strategy_id

    if persisted.strategy_ast is None:
        return sync_state

    payload = persisted.strategy_ast
    if payload.wdk_step_ids:
        for sid, wdk_step_id in payload.wdk_step_ids.items():
            if sid in graph.steps:
                sync_state.wdk_step_ids[sid] = wdk_step_id

    if payload.step_counts:
        for sid, count in payload.step_counts.items():
            if sid in graph.steps:
                sync_state.step_counts[sid] = count

    return sync_state


def build_strategy_session(
    *,
    site_id: str,
    strategy_graph: PersistedStrategyGraph | None,
) -> StrategySession:
    if strategy_graph is None or not strategy_graph.id:
        msg = (
            "build_strategy_session requires a PersistedStrategyGraph "
            "with id=str(conversation.id)"
        )
        raise ValueError(msg)

    session = StrategySession(site_id)
    name = strategy_graph.name or DEFAULT_STREAM_NAME
    graph = StrategyGraph(strategy_graph.id, name, site_id)
    if strategy_graph.strategy_ast is not None:
        payload = strategy_graph.strategy_ast
        try:
            graph.record_type = payload.record_type
            graph.name = payload.name or name
            graph.steps = flatten_tree(payload.root)
            for detached in payload.detached_roots:
                graph.steps.update(flatten_tree(detached))
            graph.recompute_roots()
            graph.last_step_id = payload.root.id
            graph.description = payload.description
            graph.save_history(f"Loaded graph: {payload.name or name}")
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(
                "Failed to load graph plan",
                error=str(e),
                graph_id=strategy_graph.id,
            )

    session.sync_state = _restore_wdk_state(strategy_graph, graph)
    session.add_graph(graph)
    return session
