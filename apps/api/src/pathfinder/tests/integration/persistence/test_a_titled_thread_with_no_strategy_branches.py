"""A thread whose name was generated before any build branches with no strategy."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.turns import name_conversation_if_unnamed
from pathfinder.tests.integration.persistence._thread_surgery import (
    add_assistant_message,
    add_user_message,
    install_fake_push,
    seed_conversation,
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


async def test_a_thread_titled_before_any_build_branches_with_no_strategy(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id, name="")
    await add_user_message(conversation_id)
    answer = await add_assistant_message(conversation_id)
    await name_conversation_if_unnamed(conversation_id, title="Kinase Hunt")

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=conversation_id,
            from_message_id=answer,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        source = await session.get(ConversationStrategy, conversation_id)
        branched = await session.get(ConversationStrategy, fork_id)
    assert source is not None
    assert (source.generated_name_steps, branched, push.seen) == ([], None, [])
