"""One thread binds at most one open analysis."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationAnalysis, User
from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

pytestmark = pytest.mark.asyncio

# Enough writers to lose an update, few enough for the test pool.
_CONCURRENT = 20


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def conversation(db_session: AsyncSession) -> Conversation:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    thread = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
    )
    db_session.add(thread)
    await db_session.commit()
    return thread


async def test_an_unbound_thread_reads_as_none(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    assert await repo.get(conversation_id=conversation.id) is None


async def test_binding_then_reading_returns_the_reference(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
    )
    view = await repo.get(conversation_id=conversation.id)
    assert view is not None
    assert view.dataset_id == "DS_53f554ec6a"
    assert view.analysis_id == "t4fszEJ"
    assert view.site_id == "plasmodb"
    assert view.revision == 0


async def test_binding_twice_replaces_the_row_rather_than_adding_one(
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    conversation: Conversation,
) -> None:
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_a",
        analysis_id="A",
    )
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_b",
        analysis_id="B",
    )
    rows = (
        (
            await db_session.execute(
                select(ConversationAnalysis).where(
                    ConversationAnalysis.conversation_id == conversation.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].analysis_id == "B"


async def test_binding_a_second_analysis_restarts_the_revision_counter(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    """A new analysis is a new document, so its edits count from zero."""
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_a",
        analysis_id="A",
    )
    await repo.increment(conversation_id=conversation.id)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_b",
        analysis_id="B",
    )
    view = await repo.get(conversation_id=conversation.id)
    assert view is not None
    assert view.revision == 0


async def test_incrementing_returns_each_new_revision_in_order(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    """Every authoring mutation reports a strictly growing number."""
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_a",
        analysis_id="A",
    )
    first = await repo.increment(conversation_id=conversation.id)
    second = await repo.increment(conversation_id=conversation.id)
    assert (first, second) == (1, 2)
    view = await repo.get(conversation_id=conversation.id)
    assert view is not None
    assert view.revision == 2


async def test_concurrent_increments_hand_out_every_revision_exactly_once(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    """Two surfaces patch the same analysis at once, and neither number is lost.

    A read-then-write increment returns duplicates under this load, and the
    revision the part carries then names two different documents.
    """
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_a",
        analysis_id="A",
    )

    revisions = await asyncio.gather(
        *(repo.increment(conversation_id=conversation.id) for _ in range(_CONCURRENT))
    )

    assert sorted(revisions) == list(range(1, _CONCURRENT + 1))
    assert len(set(revisions)) == _CONCURRENT
    view = await repo.get(conversation_id=conversation.id)
    assert view is not None
    assert view.revision == _CONCURRENT


async def test_incrementing_an_unbound_thread_reports_no_revision(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    assert await repo.increment(conversation_id=conversation.id) == 0


async def test_unbinding_removes_the_row(
    session_maker: async_sessionmaker[AsyncSession], conversation: Conversation
) -> None:
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_a",
        analysis_id="A",
    )
    await repo.unbind(conversation_id=conversation.id)
    assert await repo.get(conversation_id=conversation.id) is None


async def test_deleting_the_thread_removes_the_binding(
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    conversation: Conversation,
) -> None:
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await repo.bind(
        conversation_id=conversation.id,
        site_id="plasmodb",
        dataset_id="DS_a",
        analysis_id="A",
    )
    await db_session.delete(await db_session.get(Conversation, conversation.id))
    await db_session.commit()
    assert await repo.get(conversation_id=conversation.id) is None
