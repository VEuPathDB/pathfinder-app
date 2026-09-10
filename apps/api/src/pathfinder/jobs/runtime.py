from __future__ import annotations

import asyncio
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.runner import WorkerContextRequest
from langgraph.store.postgres.aio import AsyncPostgresStore

from pathfinder.ai.graph.runtime import Context
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.services.strategies.session_factory import (
    build_strategy_session,
    persisted_graph,
)


async def build_worker_runtime_context(
    *,
    conversation_id: UUID,
    memory_store: AsyncPostgresStore | None,
) -> Context:
    """The turn context a durable body reads, built from the thread's strategy."""
    async with async_session_factory() as session:
        found = await ConversationRepository(session).get_with_strategy(conversation_id)
    if found is None:
        msg = f"chat {conversation_id} not found"
        raise LookupError(msg)

    conversation, strategy = found
    strategy_session = build_strategy_session(
        site_id=conversation.site_id,
        strategy_graph=persisted_graph(conversation, strategy),
    )

    return Context(
        site_id=conversation.site_id,
        user_id=conversation.user_id,
        strategy_session=strategy_session,
        db_session_factory=async_session_factory,
        cancel_event=asyncio.Event(),
        experiment_id=strategy.experiment_id,
        memory_store=memory_store,
    )


async def build_worker_context(request: WorkerContextRequest) -> Context:
    """The seam the runtime calls before it runs a durable body."""
    return await build_worker_runtime_context(
        conversation_id=request.conversation_id,
        memory_store=request.memory_store,
    )
