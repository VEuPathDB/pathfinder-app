from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from assistant_core.platform import db
from assistant_core.tasks.chat_turn import defer_chat_turn
from sqlalchemy import text

from pathfinder.jobs.app import procrastinate_app
from pathfinder.persistence.repositories.thread_job import turns_in_flight
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.turn_slots import (
    TooManyTurnsError,
    require_a_free_turn,
)

_WITH_THE_DATABASE = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


async def _queue(user_id: UUID, conversation_id: UUID) -> None:
    await defer_chat_turn(
        conversation_id=conversation_id,
        payload={
            "user_id": str(user_id),
            "turnId": str(uuid4()),
            "body": {"conversationId": str(conversation_id)},
        },
    )


async def _finish(conversation_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await session.execute(
            text("UPDATE procrastinate_jobs SET status = 'failed' WHERE lock = :lock"),
            {"lock": str(conversation_id)},
        )
        await session.commit()


async def _count(user_id: UUID, sending_to: UUID) -> int:
    async with db.async_session_factory() as session:
        return await turns_in_flight(session, user_id=user_id, other_than=sending_to)


@_WITH_THE_DATABASE
async def test_only_the_users_queued_and_running_turns_count() -> None:
    researcher, someone_else = uuid4(), uuid4()
    first, second, finished, theirs = uuid4(), uuid4(), uuid4(), uuid4()
    async with procrastinate_app.open_async():
        await _queue(researcher, first)
        await _queue(researcher, second)
        await _queue(researcher, finished)
        await _queue(someone_else, theirs)
    await _finish(finished)

    assert await _count(researcher, sending_to=uuid4()) == 2
    assert await _count(someone_else, sending_to=uuid4()) == 1


@_WITH_THE_DATABASE
async def test_the_conversation_being_sent_to_is_not_counted() -> None:
    researcher, thread = uuid4(), uuid4()
    async with procrastinate_app.open_async():
        await _queue(researcher, thread)

    assert await _count(researcher, sending_to=thread) == 0


@_WITH_THE_DATABASE
async def test_a_turn_past_the_users_limit_is_refused() -> None:
    researcher = uuid4()
    async with procrastinate_app.open_async():
        for _ in range(get_settings().max_turns_in_flight_per_user):
            await _queue(researcher, uuid4())

    async with db.async_session_factory() as session:
        with pytest.raises(TooManyTurnsError):
            await require_a_free_turn(
                session, user_id=researcher, conversation_id=uuid4()
            )


@_WITH_THE_DATABASE
async def test_a_turn_under_the_users_limit_goes_ahead() -> None:
    researcher = uuid4()
    async with procrastinate_app.open_async():
        await _queue(researcher, uuid4())

    sending_to = uuid4()
    async with db.async_session_factory() as session:
        await require_a_free_turn(
            session, user_id=researcher, conversation_id=sending_to
        )

    assert await _count(researcher, sending_to=sending_to) == 1
