"""What the worker builds a turn's context from, and what it refuses to build."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select

from pathfinder.jobs.runtime import build_worker_runtime_context
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.errors import ErrorCode, StrategyAstCorruptError
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

pytestmark = pytest.mark.asyncio

_CORRUPT_AST: dict[str, Any] = {"root": "not-a-node"}


async def _seed(strategy_ast: dict[str, Any] | None) -> UUID:
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="kinases",
            ),
        )
        await session.flush()
        if strategy_ast is not None:
            session.add(
                ConversationStrategy(
                    conversation_id=conversation_id,
                    strategy_ast=strategy_ast,
                ),
            )
        await session.commit()
    return conversation_id


async def test_a_thread_with_no_strategy_builds_an_empty_graph(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """The worker starts a first turn on a thread whose strategy is not built."""
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed(None)

    context = await build_worker_runtime_context(
        conversation_id=str(conversation_id),
        task_id="t1",
    )

    graph = context.strategy_session.get_graph(None)
    assert graph is not None
    assert graph.steps == {}


async def test_a_corrupt_stored_ast_refuses_the_turn_by_name(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A row that does not parse is corruption, so the worker names it and stops."""
    del patch_app_db_engine, db_cleaner
    conversation_id = await _seed(_CORRUPT_AST)

    with pytest.raises(StrategyAstCorruptError) as excinfo:
        await build_worker_runtime_context(
            conversation_id=str(conversation_id),
            task_id="t1",
        )

    assert excinfo.value.code is ErrorCode.STRATEGY_AST_CORRUPT
    assert excinfo.value.status == 500
    assert str(conversation_id) in (excinfo.value.detail or "")

    async with async_session_factory() as session:
        stored = await session.scalar(
            select(ConversationStrategy.strategy_ast).where(
                ConversationStrategy.conversation_id == conversation_id
            )
        )
    assert stored == _CORRUPT_AST
