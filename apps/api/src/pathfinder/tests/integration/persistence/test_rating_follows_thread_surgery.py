"""A revert takes the ratings of the messages it deletes, and a branch copies none."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import select, text

from pathfinder.domain.message_rating import Rating
from pathfinder.persistence.models import MessageRating
from pathfinder.persistence.repositories.message_rating import (
    MessageRatingRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.persistence._thread_surgery import (
    FourTurns,
    four_turn_thread,
    install_fake_push,
    seed_user,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


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


async def _rate(
    thread: FourTurns, user_id: UUID, message_id: UUID, rating: Rating
) -> None:
    async with db.async_session_factory() as session:
        await MessageRatingRepository(session).set_rating(
            message_id=message_id,
            conversation_id=thread.conversation_id,
            user_id=user_id,
            rating=rating,
        )
        await session.commit()


async def _rated(conversation_id: UUID) -> list[tuple[UUID, str | None]]:
    async with db.async_session_factory() as session:
        rows = await session.scalars(
            select(MessageRating)
            .where(MessageRating.conversation_id == conversation_id)
            .order_by(MessageRating.id),
        )
        return [(row.message_id, row.rating) for row in rows]


async def test_a_revert_past_a_rated_message_removes_its_rating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    await _rate(thread, user_id, thread.answer_two, "like")
    await _rate(thread, user_id, thread.answer_four, "dislike")

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=thread.conversation_id,
            target_message_id=thread.user_three,
            user_id=user_id,
        )
        await session.commit()

    assert await _rated(thread.conversation_id) == [(thread.answer_two, "like")]


async def test_a_branch_copies_no_rating(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    await _rate(thread, user_id, thread.answer_two, "dislike")

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_two,
            user_id=user_id,
        )
        await session.commit()

    assert await _rated(fork.id) == []
    assert await _rated(thread.conversation_id) == [(thread.answer_two, "dislike")]
