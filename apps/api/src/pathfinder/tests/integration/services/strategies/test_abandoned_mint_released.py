"""A mint the thread moves away from is deleted only when nothing names it.

A refused update mints a second VEuPathDB strategy. Discarding or reverting
the turn moves the thread's id back, and the mint is then held by a gene set
of the same user, by a snapshot the cut left behind, by the user's own save,
or by another thread that names it as a saved input.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterator
from uuid import uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.services.strategies import abandoned_mint, revision_ops
from pathfinder.services.strategies.abandoned_mint import delete_released_mint
from pathfinder.services.strategies.revision_ops import restore_revision
from pathfinder.tests._support.logs import logged_events
from pathfinder.tests.integration.services.strategies._mint_release import (
    ADOPTED,
    BEFORE,
    MINTED,
    RELEASE_LOGGER,
    FakePush,
    FakeStrategyApi,
    add_gene_set,
    add_message,
    discard,
    imported,
    latest_revision,
    mark_saved,
    persist,
    record_import,
    revert,
    saved_mark,
    seed_thread,
    stored,
)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeStrategyApi:
    """The VEuPathDB strategy API the release reaches."""
    api = FakeStrategyApi()
    monkeypatch.setattr(abandoned_mint, "get_strategy_api", lambda _site: api)
    return api


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch) -> FakePush:
    fake = FakePush()
    monkeypatch.setattr(revision_ops, "materialize_strategy_snapshot", fake)
    return fake


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


async def test_discarding_a_turn_deletes_the_strategy_it_minted(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.deleted == [MINTED]
    assert await stored(session_maker, conv_id) == (BEFORE, True)


async def test_discarding_the_first_turn_deletes_the_strategy_it_minted(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The thread held no strategy when the turn opened, so the mint is cleared."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, MINTED, created=True)

    await discard(session_maker, conv_id, pre_turn_revision_id=None)

    assert site.deleted == [MINTED]
    assert await stored(session_maker, conv_id) == (None, False)


async def test_a_gene_set_taken_from_the_mint_keeps_it(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The saved gene set reads its source back from the site."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)
    await add_gene_set(session_maker, seed_user, wdk_strategy_id=MINTED)

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.attempted == []
    assert await stored(session_maker, conv_id) == (BEFORE, True)


async def test_a_restore_that_does_not_move_the_id_deletes_nothing(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, MINTED, created=True)
    revision = await latest_revision(session_maker, conv_id)

    async with session_maker() as session:
        release = await restore_revision(session, revision=revision)
        await session.commit()
    await delete_released_mint(release)

    assert site.attempted == []
    assert await stored(session_maker, conv_id) == (MINTED, True)


async def test_a_strategy_pathfinder_did_not_mint_is_never_deleted(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The thread opened a website strategy and moved to another one."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, ADOPTED, created=False)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, BEFORE, created=False)

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.attempted == []
    assert await stored(session_maker, conv_id) == (ADOPTED, False)


async def test_a_refused_delete_still_leaves_the_thread_restored(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)
    site.refuse = True

    with caplog.at_level(logging.WARNING, logger=RELEASE_LOGGER):
        await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.attempted == [MINTED]
    assert site.deleted == []
    assert await stored(session_maker, conv_id) == (BEFORE, True)
    assert logged_events(caplog.records, logger=RELEASE_LOGGER) == [
        "Failed to delete the WDK strategy an abandoned turn minted",
    ]


async def test_reverting_past_the_mint_deletes_it(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
    push: FakePush,
) -> None:
    """The cut removes the snapshot that named the mint, so nothing does."""
    conv_id = await seed_thread(db_session, seed_user)
    await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, BEFORE, created=True)
    await add_message(session_maker, conv_id, "assistant")
    minting_turn = await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, MINTED, created=True)
    await add_message(session_maker, conv_id, "assistant")

    await revert(session_maker, conv_id, target=minting_turn, user=seed_user)

    assert site.deleted == [MINTED]
    assert await stored(session_maker, conv_id) == (push.pushed[0], True)


async def test_reverting_to_a_message_after_the_mint_keeps_it(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
    push: FakePush,
) -> None:
    """The snapshot that names the mint survives the cut and could restore it."""
    conv_id = await seed_thread(db_session, seed_user)
    await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, BEFORE, created=True)
    await add_message(session_maker, conv_id, "assistant")
    await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, MINTED, created=True)
    await add_message(session_maker, conv_id, "assistant")
    later_turn = await add_message(session_maker, conv_id, "user")

    await revert(session_maker, conv_id, target=later_turn, user=seed_user)

    assert site.attempted == []
    assert await stored(session_maker, conv_id) == (push.pushed[0], True)


async def test_a_mint_the_user_marked_saved_is_kept(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """A strategy the user saved stays in the VEuPathDB account."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)
    await mark_saved(session_maker, conv_id)

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.deleted == []
    assert site.attempted == []
    assert await stored(session_maker, conv_id) == (BEFORE, True)


async def test_a_mint_another_thread_imported_is_kept(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
    push: FakePush,
) -> None:
    """A saved strategy another thread names as an input survives the revert."""
    conv_id = await seed_thread(db_session, seed_user)
    await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, BEFORE, created=True)
    await add_message(session_maker, conv_id, "assistant")
    minting_turn = await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, MINTED, created=True)
    await add_message(session_maker, conv_id, "assistant")
    consumer = await seed_thread(db_session, seed_user)
    await record_import(session_maker, consumer, wdk_strategy_id=MINTED)

    await revert(session_maker, conv_id, target=minting_turn, user=seed_user)

    assert site.deleted == []
    assert site.attempted == []
    assert await imported(session_maker, consumer) == [MINTED]
    assert await stored(session_maker, conv_id) == (push.pushed[0], True)


async def test_a_mint_clears_the_saved_mark_of_the_strategy_it_replaces(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The mark names the strategy the row holds, and a minted one is unsaved."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    await mark_saved(session_maker, conv_id)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)

    assert await saved_mark(session_maker, conv_id) is False

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.deleted == [MINTED]


async def test_a_restore_carries_the_saved_mark_of_the_snapshot(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The mark follows the restored strategy, so a later move keeps it.

    The thread saves its first mint, a turn mints a second, and the discard
    restores the first. A revert past it then finds a saved strategy.
    """
    conv_id = await seed_thread(db_session, seed_user)
    first_turn = await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, BEFORE, created=True)
    await mark_saved(session_maker, conv_id)
    await add_message(session_maker, conv_id, "assistant")
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await add_message(session_maker, conv_id, "user")
    await persist(conv_id, session_maker, MINTED, created=True)

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert await saved_mark(session_maker, conv_id) is True

    await revert(session_maker, conv_id, target=first_turn, user=seed_user)

    assert site.deleted == [MINTED]
    assert await stored(session_maker, conv_id) == (None, False)


async def test_a_mint_the_user_saved_on_the_website_is_kept(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The site holds the saved mark the local row never learned."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)
    site.saved_on_site = True

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.deleted == []
    assert site.attempted == []
    assert site.read == [MINTED]
    assert await saved_mark(session_maker, conv_id) is False
    assert await stored(session_maker, conv_id) == (BEFORE, True)


async def test_a_mint_the_site_does_not_answer_for_is_kept(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A saved mark the site cannot answer keeps the strategy."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)
    site.read_refused = True

    with caplog.at_level(logging.WARNING, logger=RELEASE_LOGGER):
        await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.deleted == []
    assert site.attempted == []
    assert site.read == [MINTED]
    assert logged_events(caplog.records, logger=RELEASE_LOGGER) == [
        "Abandoned WDK strategy kept: the site did not answer the saved mark",
    ]
    assert await stored(session_maker, conv_id) == (BEFORE, True)


async def test_a_mint_the_site_reports_unsaved_is_deleted(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    site: FakeStrategyApi,
) -> None:
    """The delete follows the site's own answer, not the local row alone."""
    conv_id = await seed_thread(db_session, seed_user)
    await persist(conv_id, session_maker, BEFORE, created=True)
    pre_turn = (await latest_revision(session_maker, conv_id)).id
    await persist(conv_id, session_maker, MINTED, created=True)

    await discard(session_maker, conv_id, pre_turn_revision_id=pre_turn)

    assert site.read == [MINTED]
    assert site.deleted == [MINTED]
