from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.serde import build_checkpoint_serde
from assistant_core.persistence.models import Conversation, ConversationEvent, Message
from assistant_core.platform import db
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from strategist.ai.graph.state import StrategyDomainState
from strategist.assistants.strategist_spec import STRATEGIST_CHECKPOINT_TYPES
from strategist.domain.evidence import NamedControlSet
from strategist.persistence.models import User
from strategist.platform.config import get_settings
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID

CHUNKS = (
    {"type": "start", "messageId": "m-1"},
    {"type": "text-start", "id": "t-1"},
    {"type": "text-delta", "id": "t-1", "delta": "Kinases on chromosome 3."},
    {"type": "text-end", "id": "t-1"},
    {"type": "finish"},
    {"type": "done"},
)


OWNER_READ = (
    {"type": "start", "messageId": "m-2"},
    {"type": "tool-input-start", "toolCallId": "c-1", "toolName": "list_my_threads"},
    {
        "type": "tool-input-available",
        "toolCallId": "c-1",
        "toolName": "list_my_threads",
        "input": {},
    },
    {
        "type": "tool-output-available",
        "toolCallId": "c-1",
        "output": {"threads": ["Malaria antigens"]},
    },
    {"type": "finish"},
    {"type": "done"},
)

SERDE = build_checkpoint_serde(STRATEGIST_CHECKPOINT_TYPES)


async def seed_owners_state(
    session_maker: async_sessionmaker[AsyncSession], thread: UUID
) -> None:
    kind, blob = SERDE.dumps_typed(
        StrategyDomainState(
            original_request="Kinases on chromosome 3",
            control_sets=[NamedControlSet(id="cs-1", name="owner controls")],
        )
    )
    async with session_maker() as session:
        session.add_all(
            ConversationEvent(conversation_id=thread, chunk=chunk)
            for chunk in OWNER_READ
        )
        await session.execute(
            text(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, "
                "parent_checkpoint_id, type, checkpoint, metadata) VALUES "
                "(:thread, '', 'k-1', NULL, 'msgpack', CAST(:checkpoint AS jsonb), "
                "'{}'::jsonb)"
            ),
            {
                "thread": str(thread),
                "checkpoint": json.dumps(
                    {
                        "id": "k-1",
                        "ts": "2026-11-09T12:00:00+00:00",
                        "channel_versions": {"domain": "1"},
                    }
                ),
            },
        )
        await session.execute(
            text(
                "INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, "
                "version, type, blob) VALUES (:thread, '', 'domain', '1', :type, :blob)"
            ),
            {"thread": str(thread), "type": kind, "blob": blob},
        )
        await session.commit()


def share_path(conversation_id: UUID) -> str:
    return f"/api/v1/conversations/{conversation_id}/share"


async def seed_thread(
    session_maker: async_sessionmaker[AsyncSession], user_id: UUID
) -> UUID:
    conversation_id = uuid4()
    async with session_maker() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id))
            await session.flush()
        session.add(
            Conversation(
                assistant_id=STRATEGIST_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="kinases",
            )
        )
        await session.flush()
        session.add(
            Message(
                id=uuid4(),
                conversation_id=conversation_id,
                role="assistant",
                metadata_={"mode": "explore"},
            )
        )
        session.add_all(
            ConversationEvent(conversation_id=conversation_id, chunk=chunk)
            for chunk in CHUNKS
        )
        await session.commit()
    return conversation_id


@pytest.fixture
async def checkpoint_tables(patch_app_db_engine: None) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield
    async with db.async_session_factory() as session:
        await session.execute(
            text("TRUNCATE TABLE checkpoints, checkpoint_blobs, checkpoint_writes")
        )
        await session.commit()


def anonymous(app: ASGIApp) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
