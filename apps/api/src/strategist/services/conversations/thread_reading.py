from __future__ import annotations

from uuid import UUID

from assistant_core.conversation.authz import get_visible_conversation
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from strategist.persistence.repositories import ConversationRepository
from strategist.services.conversations.account_reads import account_reads_allowed
from strategist.services.eval_data.chunk_reader import read_turns
from strategist.services.eval_data.extraction import logged_chunks

_LAST_TURNS = 20


class ThreadListing(CamelModel):
    conversation_id: UUID
    name: str
    site_id: str


class ThreadTurn(CamelModel):
    request: str
    reply: str


class ThreadReading(CamelModel):
    conversation_id: UUID
    name: str
    site_id: str
    turns: list[ThreadTurn] = Field(default_factory=list)


async def standing_leave(conversation_id: UUID, user_id: UUID) -> bool:
    async with async_session_factory() as session:
        return await account_reads_allowed(
            session, conversation_id=conversation_id, user_id=user_id
        )


async def other_threads(user_id: UUID, *, but: UUID) -> list[ThreadListing]:
    async with async_session_factory() as session:
        rows = await ConversationRepository(session).list_conversations(user_id)
    return [
        ThreadListing(
            conversation_id=conversation.id,
            name=conversation.name,
            site_id=conversation.site_id,
        )
        for conversation, _ in rows
        if conversation.id != but
    ]


async def read_thread(user_id: UUID, conversation_id: UUID) -> ThreadReading:
    async with async_session_factory() as session:
        conversation = await get_visible_conversation(
            ConversationRepository(session), conversation_id, user_id
        )
        chunks = await logged_chunks(session, conversation_id)
    turns = read_turns(chunks)[-_LAST_TURNS:]
    return ThreadReading(
        conversation_id=conversation.id,
        name=conversation.name,
        site_id=conversation.site_id,
        turns=[ThreadTurn(request=t.request, reply=t.reply) for t in turns],
    )


__all__ = [
    "ThreadListing",
    "ThreadReading",
    "ThreadTurn",
    "other_threads",
    "read_thread",
    "standing_leave",
]
