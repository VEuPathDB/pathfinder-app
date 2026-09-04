"""The turn-scoped reads and writes the assistant graph makes on a thread."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationStrategyView, User
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.services.conversations.turns import (
    load_conversation,
    name_conversation_if_unnamed,
    name_turn_strategy_revision,
    turn_start_revision_id,
)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        yield session


async def _thread(session: AsyncSession, *, name: str = "") -> Conversation:
    owner = User(id=uuid4())
    conversation = Conversation(user_id=owner.id, site_id="plasmodb", name=name)
    session.add_all([owner, conversation])
    await session.flush()
    await session.commit()
    return conversation


async def test_load_conversation_reads_the_row(db_session: AsyncSession) -> None:
    conversation = await _thread(db_session, name="kinases")

    loaded = await load_conversation(conversation.id)

    assert loaded is not None
    assert (loaded.name, loaded.site_id) == ("kinases", "plasmodb")


async def test_load_conversation_reports_no_row(db_session: AsyncSession) -> None:
    conversation = await _thread(db_session, name="kinases")

    rows = [
        await load_conversation(conversation.id),
        await load_conversation(uuid4()),
    ]

    assert [None if row is None else row.name for row in rows] == ["kinases", None]


async def test_an_unnamed_thread_takes_the_generated_title(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)

    named = await name_conversation_if_unnamed(conversation.id, title="Kinase hunt")

    assert named is True
    reloaded = await load_conversation(conversation.id)
    assert reloaded is not None
    assert reloaded.name == "Kinase hunt"


async def test_a_named_thread_keeps_its_name(db_session: AsyncSession) -> None:
    conversation = await _thread(db_session, name="chosen by the user")

    named = await name_conversation_if_unnamed(conversation.id, title="Kinase hunt")

    assert named is False
    reloaded = await load_conversation(conversation.id)
    assert reloaded is not None
    assert reloaded.name == "chosen by the user"


async def test_turn_start_revision_id_names_the_newest_snapshot(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)
    before = await turn_start_revision_id(conversation.id)
    repo = StrategyRevisionRepository(db_session)
    first = await repo.record(
        conversation.id,
        ConversationStrategyView(record_type="transcript", step_count=1),
    )
    second = await repo.record(
        conversation.id,
        ConversationStrategyView(record_type="transcript", step_count=2),
    )
    await db_session.commit()
    assert first is not None
    assert second is not None

    assert [before, await turn_start_revision_id(conversation.id)] == [
        None,
        second.id,
    ]


async def test_naming_a_revision_binds_it_to_the_turn_message(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)
    revision = await StrategyRevisionRepository(db_session).record(
        conversation.id,
        ConversationStrategyView(record_type="transcript", step_count=1),
    )
    await db_session.commit()
    assert revision is not None
    message_id = uuid4()

    await name_turn_strategy_revision(
        async_session_factory,
        conversation_id=conversation.id,
        message_id=message_id,
    )

    async with async_session_factory() as session:
        named = await StrategyRevisionRepository(session).named_by(
            conversation.id,
            message_id=message_id,
        )
    assert named is not None
    assert named.id == revision.id
