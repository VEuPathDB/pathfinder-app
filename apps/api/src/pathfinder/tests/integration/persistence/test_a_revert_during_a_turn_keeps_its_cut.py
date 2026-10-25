from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.persistence.models import ConversationEvent
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform import db
from sqlalchemy import select, text

from pathfinder.platform.errors import RevertRefusedError
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.persistence._busy_thread import (
    queue_turn,
    set_turn_status,
)
from pathfinder.tests.integration.persistence._thread_surgery import (
    FourTurns,
    add_user_message,
    four_turn_thread,
    install_fake_push,
    message_ids,
    seed_user,
)


@pytest.fixture
async def _no_jobs_left(patch_app_db_engine: None) -> AsyncIterator[None]:
    del patch_app_db_engine
    yield
    async with db.async_session_factory() as session:
        await session.execute(text("TRUNCATE TABLE procrastinate_jobs CASCADE"))
        await session.commit()


async def _fake_turn(
    thread: FourTurns,
    user_id: UUID,
    *,
    streaming: asyncio.Event,
    resume: asyncio.Event,
) -> None:
    await add_user_message(thread.conversation_id)
    await queue_turn(thread.conversation_id, user_id)
    await set_turn_status(thread.conversation_id, "doing")
    turn_id = uuid4()
    writer = ChatEventWriter(conversation_id=thread.conversation_id, turn_id=turn_id)
    await writer.write({"type": "start", "messageId": str(turn_id)})
    await writer.write({"type": "text-start", "id": "t1"})
    await writer.write({"type": "text-delta", "id": "t1", "delta": "Checking"})
    streaming.set()
    await resume.wait()
    await writer.write({"type": "text-delta", "id": "t1", "delta": " orthologs"})
    await writer.write({"type": "text-end", "id": "t1"})
    await writer.write({"type": "finish"})
    async with db.async_session_factory() as session:
        await MessagesRepository(session).upsert_message(
            message_id=turn_id,
            conversation_id=thread.conversation_id,
            role="assistant",
            metadata={"usage": {"totalTokens": 40, "costUsd": "0.001"}},
        )
        await session.commit()
    await writer.write({"type": "done"})
    await set_turn_status(thread.conversation_id, "succeeded")


async def _revert(thread: FourTurns, user_id: UUID) -> str:
    try:
        async with db.async_session_factory() as session:
            await revert_conversation_to_message(
                session,
                conversation_id=thread.conversation_id,
                target_message_id=thread.user_three,
                user_id=user_id,
            )
            await session.commit()
    except RevertRefusedError:
        return "refused"
    return "reverted"


async def _turns_in_log(conversation_id: UUID) -> set[str]:
    async with db.async_session_factory() as session:
        return {
            str(turn_id)
            for turn_id in (
                await session.scalars(
                    select(ConversationEvent.turn_id).where(
                        ConversationEvent.conversation_id == conversation_id,
                    ),
                )
            )
        }


@pytest.mark.usefixtures("db_cleaner", "_no_jobs_left")
async def test_a_revert_during_a_streaming_turn_never_gets_its_tail_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    streaming, resume = asyncio.Event(), asyncio.Event()
    turn = asyncio.create_task(
        _fake_turn(thread, user_id, streaming=streaming, resume=resume),
    )

    await streaming.wait()
    during_the_turn = await _revert(thread, user_id)
    resume.set()
    await turn
    after_the_turn = await _revert(thread, user_id)

    surviving = [str(thread.user_one), str(thread.answer_two)]
    assert await message_ids(thread.conversation_id) == surviving
    assert await _turns_in_log(thread.conversation_id) == set(surviving)
    assert (during_the_turn, after_the_turn) == ("refused", "reverted")
