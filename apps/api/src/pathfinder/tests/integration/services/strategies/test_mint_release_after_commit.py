"""The VEuPathDB delete runs after the local writes are committed.

A commit that fails must leave the site as it was: a row that survives the
failure still names the strategy.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.conversation import turn_stop
from pathfinder.ai.conversation.turn_stop import restore_pre_turn_strategy
from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.services.strategies import abandoned_mint
from pathfinder.tests.integration.services.strategies._mint_release import (
    BEFORE,
    MINTED,
    FakeStrategyApi,
    add_message,
    latest_revision,
    persist,
    seed_thread,
    stored,
)

REFUSED = "the transaction failed"


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeStrategyApi:
    """The VEuPathDB strategy API the release reaches."""
    api = FakeStrategyApi()
    monkeypatch.setattr(abandoned_mint, "get_strategy_api", lambda _site: api)
    return api


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.commit()
    return user


def _refuse_the_commit(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make the session the stop path opens raise on commit."""

    async def _raise() -> None:
        raise RuntimeError(REFUSED)

    @asynccontextmanager
    async def _open() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            monkeypatch.setattr(session, "commit", _raise)
            yield session

    monkeypatch.setattr(turn_stop, "async_session_factory", _open)


async def test_a_stop_whose_commit_fails_deletes_nothing_on_the_site(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)
    _refuse_the_commit(session_maker, monkeypatch)

    with pytest.raises(RuntimeError, match=REFUSED):
        await restore_pre_turn_strategy(conv_id, pre_turn_revision_id=pre_turn)

    assert site.attempted == []
    assert await stored(session_maker, conv_id) == (MINTED, True)


async def test_a_stop_that_commits_deletes_the_mint(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)

    await restore_pre_turn_strategy(conv_id, pre_turn_revision_id=pre_turn)

    assert site.deleted == [MINTED]
    assert await stored(session_maker, conv_id) == (BEFORE, True)


async def test_a_revert_asks_the_site_for_nothing_before_its_caller_commits(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The service hands the release back; the route runs it after the commit."""
    conv_id = await seed_thread(db_session, seed_user)
    first_turn = await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, MINTED, created=True)
    await add_message(session_maker, conv_id, "assistant")

    async with session_maker() as session:
        release = await revert_conversation_to_message(
            session,
            conversation_id=conv_id,
            target_message_id=first_turn,
            user_id=seed_user.id,
        )
        assert site.attempted == []
        await session.commit()

    assert release is not None
    assert release.wdk_strategy_id == MINTED
    assert site.attempted == []
