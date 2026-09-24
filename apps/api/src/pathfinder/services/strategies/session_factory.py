"""Helpers for hydrating in-memory strategy session context for agents."""

from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.conversation import (
    DEFAULT_CONVERSATION_NAME,
)
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyAst, flatten_tree

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.persistence.models import (
    ConversationStrategyView,
    PersistedStrategyGraph,
)
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import StrategyAstCorruptError, StrategyCompilationError
from pathfinder.services.strategies.sync import build_step_tree_from_graph
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

    _restore_wdk_tree(payload, sync_state)
    return sync_state


def _restore_wdk_tree(payload: StrategyAst, sync_state: WDKSyncState) -> None:
    """A stored strategy whose last push failed nowhere is the tree WDK holds."""
    if payload.wdk_push_errors:
        sync_state.wdk_push_errors.update(payload.wdk_push_errors)
        return
    if sync_state.wdk_strategy_id is None:
        return
    try:
        sync_state.wdk_step_tree = build_step_tree_from_graph(
            payload.root, sync_state.wdk_step_ids
        )
    except StrategyCompilationError:
        sync_state.wdk_step_tree = None


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
    payload = strategy_graph.strategy_ast
    # The thread owns the name; the stored strategy carries a copy of it.
    name = (
        strategy_graph.name
        or (payload.name if payload is not None else None)
        or DEFAULT_CONVERSATION_NAME
    )
    graph = StrategyGraph(strategy_graph.id, name, site_id)
    if payload is not None:
        try:
            graph.record_type = payload.record_type
            graph.steps = flatten_tree(payload.root)
            for detached in payload.detached_roots:
                graph.steps.update(flatten_tree(detached))
            graph.recompute_roots()
            graph.last_step_id = payload.root.id
            graph.description = payload.description
            graph.note_words(StepWords.of(payload))
            graph.save_history(f"Loaded graph: {name}")
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(
                "Failed to load graph plan",
                error=str(e),
                graph_id=strategy_graph.id,
            )

    session.sync_state = _restore_wdk_state(strategy_graph, graph)
    session.add_graph(graph)
    return session


async def stored_strategy_session(
    db: AsyncSession, conversation_id: UUID, site_id: str
) -> StrategySession | None:
    """The thread's strategy as its stored row holds it, or None for no thread."""
    found = await ConversationRepository(db).get_with_strategy(conversation_id)
    if found is None:
        return None
    return build_strategy_session(
        site_id=site_id, strategy_graph=persisted_graph(*found)
    )
