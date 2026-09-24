"""One rating row per message per user, and the case keys it governs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.schemas import MemoryValue
from assistant_core.persistence.models import Conversation, Message
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.message_rating import Rating, WithheldCase
from pathfinder.persistence.models import MessageRating, User
from pathfinder.persistence.repositories.message_rating import (
    MessageRatingRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


@dataclass(frozen=True)
class _Thread:
    user_id: UUID
    conversation_id: UUID
    messages: tuple[UUID, UUID]


@pytest.fixture
async def thread(session_maker: async_sessionmaker[AsyncSession]) -> _Thread:
    user_id = uuid4()
    conversation_id = uuid4()
    messages = (uuid4(), uuid4())
    async with session_maker() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
            ),
        )
        await session.flush()
        for message_id in messages:
            session.add(
                Message(
                    id=message_id,
                    conversation_id=conversation_id,
                    role="assistant",
                    metadata_={},
                ),
            )
        await session.commit()
    return _Thread(user_id, conversation_id, messages)


def _withheld(key: str) -> WithheldCase:
    return WithheldCase(
        key=key,
        value=MemoryValue(
            kind="case",
            name="kinases",
            summary="find every kinase: 142",
            content={"root_count": 142},
            created_at=datetime(2026, 9, 24, tzinfo=UTC),
        ),
    )


async def test_a_rating_changed_twice_leaves_one_row(
    thread: _Thread,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    message_id = thread.messages[0]
    ratings: tuple[Rating, ...] = ("like", "dislike", "like")
    for rating in ratings:
        async with session_maker() as session:
            await MessageRatingRepository(session).set_rating(
                message_id=message_id,
                conversation_id=thread.conversation_id,
                user_id=thread.user_id,
                rating=rating,
            )
            await session.commit()

    async with session_maker() as session:
        count = await session.scalar(select(func.count()).select_from(MessageRating))
        rated = await MessageRatingRepository(session).list_rated(
            thread.conversation_id, user_id=thread.user_id
        )

    assert count == 1
    assert [(row.message_id, row.rating) for row in rated] == [(message_id, "like")]


async def test_a_cleared_rating_is_not_listed_and_keeps_its_keys(
    thread: _Thread,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    message_id = thread.messages[0]
    async with session_maker() as session:
        repo = MessageRatingRepository(session)
        await repo.record_turn_cases(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=thread.user_id,
            keys=["case:abc"],
            withheld=[],
        )
        await repo.set_rating(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=thread.user_id,
            rating="dislike",
        )
        cleared = await repo.set_rating(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=thread.user_id,
            rating=None,
        )
        await session.commit()
        rated = await repo.list_rated(thread.conversation_id, user_id=thread.user_id)

    assert rated == []
    assert cleared.rating is None
    assert cleared.rated_at is None
    assert cleared.case_keys == ["case:abc"]


async def test_recording_the_cases_twice_unions_the_keys_and_the_withheld(
    thread: _Thread,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    message_id = thread.messages[0]
    async with session_maker() as session:
        repo = MessageRatingRepository(session)
        await repo.record_turn_cases(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=thread.user_id,
            keys=["case:abc"],
            withheld=[_withheld("case:abc")],
        )
        await repo.record_turn_cases(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=thread.user_id,
            keys=["case:abc", "case:def"],
            withheld=[_withheld("case:def")],
        )
        await session.commit()
        row = await repo.get(message_id, user_id=thread.user_id)

    assert row is not None
    assert row.rating is None
    assert row.case_keys == ["case:abc", "case:def"]
    assert [case.key for case in row.withheld_cases] == ["case:abc", "case:def"]
    assert row.withheld_cases[0].value.content == {"root_count": 142}


async def test_other_ratings_are_read_by_the_keys_they_share(
    thread: _Thread,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    first, second = thread.messages
    async with session_maker() as session:
        repo = MessageRatingRepository(session)
        rated: tuple[tuple[UUID, list[str], Rating], ...] = (
            (first, ["case:abc"], "dislike"),
            (second, ["case:xyz"], "like"),
        )
        for message_id, keys, rating in rated:
            await repo.record_turn_cases(
                message_id=message_id,
                conversation_id=thread.conversation_id,
                user_id=thread.user_id,
                keys=keys,
                withheld=[],
            )
            await repo.set_rating(
                message_id=message_id,
                conversation_id=thread.conversation_id,
                user_id=thread.user_id,
                rating=rating,
            )
        await session.commit()
        sharing = await repo.others_for_keys(
            user_id=thread.user_id, keys=["case:abc"], excluding=second
        )
        excluded = await repo.others_for_keys(
            user_id=thread.user_id, keys=["case:abc"], excluding=first
        )

    assert [(other.rating, other.case_keys) for other in sharing] == [
        ("dislike", ("case:abc",))
    ]
    assert excluded == []


async def test_deleting_the_message_deletes_its_rating(
    thread: _Thread,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A revert deletes the message rows, and their ratings go with them."""
    message_id = thread.messages[0]
    async with session_maker() as session:
        await MessageRatingRepository(session).set_rating(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=thread.user_id,
            rating="like",
        )
        await session.commit()
    async with session_maker() as session:
        await session.execute(delete(Message).where(Message.id == message_id))
        await session.commit()

    async with session_maker() as session:
        remaining = await session.scalar(
            select(func.count())
            .select_from(MessageRating)
            .where(MessageRating.message_id == message_id)
        )
    assert remaining == 0
