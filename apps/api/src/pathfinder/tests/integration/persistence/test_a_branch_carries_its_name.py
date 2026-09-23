"""A branch pushes its strategy under the branch thread's name."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations import fork_strategy
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.strategies.materialize import MaterializedStrategy
from pathfinder.tests.integration.persistence._thread_surgery import (
    four_turn_thread,
    install_fake_push,
    seed_user,
)


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture(autouse=True)
async def _truncate_langgraph_tables() -> AsyncIterator[None]:
    yield
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes RESTART IDENTITY",
            ),
        )
        await session.commit()


async def test_the_branch_strategy_takes_the_branch_threads_name(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    names: list[str] = []

    async def _named_push(**kwargs: Any) -> MaterializedStrategy:
        names.append(kwargs["name"])
        return await push(**kwargs)

    monkeypatch.setattr(fork_strategy, "materialize_strategy_snapshot", _named_push)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    fork_id = await _fork(thread.conversation_id, thread.answer_two, user_id)

    assert fork_id != thread.conversation_id
    assert names == ["protease work (branch)"]


async def _fork(source: UUID, anchor: UUID, user_id: UUID) -> UUID:
    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        return fork.id
