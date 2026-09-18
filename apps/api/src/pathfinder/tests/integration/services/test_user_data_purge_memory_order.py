"""The relational purge commits before a memory is deleted."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, MemoryTombstoneRow
from assistant_core.platform.context import application_id_ctx
from assistant_core.platform.db import async_session_factory
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.user_data import purge_user_data


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        yield session


async def _user_with_a_thread(session: AsyncSession) -> User:
    owner = User(id=uuid4())
    session.add_all(
        [
            owner,
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                user_id=owner.id,
                application_id="pathfinder",
                site_id="plasmodb",
                name="a thread",
            ),
        ],
    )
    await session.flush()
    await session.commit()
    return owner


async def _seed_memory(store: MemoryStore, owner: User) -> None:
    await store.put(
        user_id=owner.id,
        value=MemoryValue(
            kind="knowledge",
            name="a fact",
            summary="a fact",
            tags=[],
            content={"note": "a fact"},
            created_at=datetime.now(UTC),
        ),
    )


async def _held(store: MemoryStore, owner: User) -> int:
    return len(await store.list_all(user_id=owner.id, kind="knowledge"))


async def _threads(owner: User) -> int:
    async with async_session_factory() as verify:
        return (
            await verify.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == owner.id),
            )
            or 0
        )


async def test_a_commit_that_fails_leaves_the_memories_in_place(
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A memory goes only after the rows that named the user are gone."""
    owner = await _user_with_a_thread(db_session)
    await _seed_memory(app_memory_store, owner)

    async def _refuse() -> None:
        msg = "the purge transaction failed"
        raise RuntimeError(msg)

    token = application_id_ctx.set("pathfinder")
    try:
        async with session_maker() as session:
            monkeypatch.setattr(session, "commit", _refuse)
            with pytest.raises(RuntimeError, match="the purge transaction failed"):
                await purge_user_data(
                    session=session,
                    user_id=owner.id,
                    site_id=None,
                    delete_wdk=False,
                    memory_store=app_memory_store,
                )
    finally:
        application_id_ctx.reset(token)

    assert await _held(app_memory_store, owner) == 1
    assert await _threads(owner) == 1


async def test_the_purge_takes_the_memories_and_their_tombstones_after_the_commit(
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The committed purge still reports and removes every memory."""
    owner = await _user_with_a_thread(db_session)
    await _seed_memory(app_memory_store, owner)

    token = application_id_ctx.set("pathfinder")
    try:
        async with session_maker() as session:
            result = await purge_user_data(
                session=session,
                user_id=owner.id,
                site_id=None,
                delete_wdk=False,
                memory_store=app_memory_store,
            )
    finally:
        application_id_ctx.reset(token)

    assert result.memories == 1
    assert await _held(app_memory_store, owner) == 0
    async with session_maker() as verify:
        tombstones = await verify.scalar(
            select(func.count())
            .select_from(MemoryTombstoneRow)
            .where(MemoryTombstoneRow.user_id == owner.id),
        )
    assert tombstones == 0
