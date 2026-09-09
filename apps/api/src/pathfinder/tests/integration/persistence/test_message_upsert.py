from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation, Message
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform import db
from sqlalchemy import select

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.mark.asyncio
async def test_upsert_replaces_metadata(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    conversation_id = uuid4()
    message_id = uuid4()

    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="t",
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        await MessagesRepository(session).upsert_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="assistant",
            metadata={"usage": {"totalTokens": 100, "costUsd": "0.01"}},
        )
        await session.commit()

    async with db.async_session_factory() as session:
        await MessagesRepository(session).upsert_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="assistant",
            metadata={"usage": {"totalTokens": 250, "costUsd": "0.03"}},
        )
        await session.commit()

    async with db.async_session_factory() as session:
        rows = (
            await session.scalars(
                select(Message).where(Message.conversation_id == conversation_id),
            )
        ).all()
        assert len(rows) == 1, rows
        final = rows[0]
        assert final.id == message_id
        assert final.metadata_ == {
            "usage": {"totalTokens": 250, "costUsd": "0.03"},
        }


@pytest.mark.asyncio
async def test_sum_usage_reads_partial_turn_metadata(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    conversation_id = uuid4()
    message_id = uuid4()

    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="t",
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        repo = MessagesRepository(session)
        await repo.upsert_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="assistant",
            metadata={"usage": {"totalTokens": 517, "costUsd": "0.042"}},
        )
        await session.commit()

    async with db.async_session_factory() as session:
        total_tokens, total_cost = await MessagesRepository(
            session,
        ).sum_usage_for_conversation(conversation_id)
        assert total_tokens == 517
        assert str(total_cost) == "0.042"


@pytest.mark.asyncio
async def test_insert_message_is_idempotent_on_same_id(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    conversation_id = uuid4()
    message_id = uuid4()

    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="t",
            ),
        )
        await session.commit()

    original_meta = {"siteId": "plasmodb", "mode": "strategy"}

    async with db.async_session_factory() as session:
        await MessagesRepository(session).insert_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="user",
            metadata=original_meta,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        await MessagesRepository(session).insert_message(
            message_id=message_id,
            conversation_id=conversation_id,
            role="user",
            metadata={"siteId": "plasmodb", "mode": "different"},
        )
        await session.commit()

    async with db.async_session_factory() as session:
        rows = (
            await session.scalars(
                select(Message).where(Message.id == message_id),
            )
        ).all()
        assert len(rows) == 1
        kept = rows[0]
        assert kept.metadata_ == original_meta
