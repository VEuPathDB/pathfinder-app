"""A conversation that is deleted leaves none of its graph state behind."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import text

from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.user_data import purge_user_data


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
    async with async_session_factory() as session:
        await session.execute(
            text("TRUNCATE TABLE checkpoints, checkpoint_blobs, checkpoint_writes")
        )
        await session.commit()


async def _thread(user_id: UUID, parent: UUID | None = None) -> UUID:
    """A conversation with one checkpoint, one blob and one pending write."""
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="kinases",
                parent_conversation_id=parent,
            )
        )
        await session.flush()
        thread = {"tid": str(conversation_id)}
        await session.execute(
            text(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, "
                "checkpoint, metadata) VALUES (:tid, '', 'c1', '{}', '{}')"
            ),
            thread,
        )
        await session.execute(
            text(
                "INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, "
                "version, type, blob) VALUES (:tid, '', 'messages', '1', 'bytes', "
                "'\\x00')"
            ),
            thread,
        )
        await session.execute(
            text(
                "INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, "
                "checkpoint_id, task_id, idx, channel, blob) VALUES "
                "(:tid, '', 'c1', 't1', 0, 'messages', '\\x00')"
            ),
            thread,
        )
        await session.commit()
    return conversation_id


_COUNTS = {
    "checkpoints": text("SELECT count(*) FROM checkpoints WHERE thread_id = any(:ids)"),
    "checkpoint_blobs": text(
        "SELECT count(*) FROM checkpoint_blobs WHERE thread_id = any(:ids)"
    ),
    "checkpoint_writes": text(
        "SELECT count(*) FROM checkpoint_writes WHERE thread_id = any(:ids)"
    ),
}


async def _held(conversation_ids: list[UUID]) -> dict[str, int]:
    """How many rows of each checkpoint table name one of these threads."""
    ids = [str(c) for c in conversation_ids]
    async with async_session_factory() as session:
        return {
            table: await session.scalar(count, {"ids": ids}) or 0
            for table, count in _COUNTS.items()
        }


_NONE = {"checkpoints": 0, "checkpoint_blobs": 0, "checkpoint_writes": 0}


async def _user() -> UUID:
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


async def test_a_deleted_conversation_and_its_branches_keep_no_checkpoint(
    db_cleaner: None,
) -> None:
    del db_cleaner
    user_id = await _user()
    root = await _thread(user_id)
    branch = await _thread(user_id, parent=root)
    other = await _thread(user_id)

    async with async_session_factory() as session:
        await ConversationService(session).delete(
            root, user_id, delete_from_wdk=False, cascade=True
        )

    assert await _held([root, branch]) == _NONE
    assert await _held([other]) == {
        "checkpoints": 1,
        "checkpoint_blobs": 1,
        "checkpoint_writes": 1,
    }


async def test_a_purge_keeps_no_checkpoint_of_a_thread_it_deletes(
    db_cleaner: None, app_memory_store: MemoryStore
) -> None:
    del db_cleaner
    user_id = await _user()
    threads = [await _thread(user_id), await _thread(user_id)]

    async with async_session_factory() as session:
        await purge_user_data(
            session=session,
            user_id=user_id,
            site_id=None,
            delete_wdk=True,
            memory_store=app_memory_store,
        )

    assert await _held(threads) == _NONE
