from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform import db

from strategist.persistence.models import User
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.services.conversations.duplicate import duplicate_conversation
from strategist.services.conversations.fork import fork_conversation
from strategist.services.conversations.revert import revert_conversation_to_message
from strategist.services.conversations.thread_mode import (
    keep_thread_mode,
    thread_mode_of,
)


async def _explore_thread(user_id: UUID) -> tuple[UUID, list[UUID]]:
    conversation_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                assistant_id=STRATEGIST_ASSISTANT_ID,
                name="Stages",
            )
        )
        await session.flush()
        await keep_thread_mode(session, conversation_id=conversation_id, mode="explore")
        await session.commit()
    message_ids: list[UUID] = []
    for role in ("user", "assistant", "user", "assistant"):
        async with db.async_session_factory() as session:
            message_id = uuid4()
            await MessagesRepository(session).insert_message(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                metadata={"mode": "explore"},
            )
            await session.commit()
            message_ids.append(message_id)
    return conversation_id, message_ids


async def _mode(conversation_id: UUID) -> str:
    async with db.async_session_factory() as session:
        return await thread_mode_of(session, conversation_id)


async def test_a_branch_opens_on_the_source_threads_mode(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id, message_ids = await _explore_thread(user_id)
    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_id,
            from_message_id=message_ids[1],
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id
    assert await _mode(fork_id) == "explore"


async def test_a_copy_opens_on_the_source_threads_mode(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    source_id, _ = await _explore_thread(user_id)
    async with db.async_session_factory() as session:
        copy = await duplicate_conversation(session, source_id, user_id)
    assert await _mode(copy.id) == "explore"


async def test_a_revert_keeps_the_threads_mode(
    patch_app_db_engine: None, db_cleaner: None
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    conversation_id, message_ids = await _explore_thread(user_id)
    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=message_ids[2],
            user_id=user_id,
        )
        await session.commit()
    assert await _mode(conversation_id) == "explore"
