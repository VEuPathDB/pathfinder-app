"""A researcher's rating of one assistant message, and what the product does with it.

A rating decides the case memories its message wrote, stages a disliked
message as an eval case, and reports the rating with the turn's usage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from assistant_core.conversation.authz import get_visible_conversation
from assistant_core.memory.autowrite import MemoryCandidate, auto_write_memories
from assistant_core.memory.deadline import memory_store_deadline
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.persistence.models import Conversation, Message
from assistant_core.platform.db import DBSessionFactory, async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.message_rating import (
    CASE_KIND,
    Rating,
    WithheldCase,
    partition_cases,
    settle_cases,
)
from pathfinder.persistence.models import MessageRatingView
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.persistence.repositories.message_rating import (
    MessageRatingRepository,
)
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.platform.langfuse.actions import (
    ProductActionEvent,
    record_product_action,
)
from pathfinder.services.eval_data.rated import (
    stage_disliked_message,
    unstage_rated_message,
)

__all__ = [
    "RatedMessage",
    "RatedMessageList",
    "TurnMemories",
    "clear_message_rating",
    "list_message_ratings",
    "rate_message",
    "rating_lock",
    "write_turn_memories",
]


class RatedMessage(CamelModel):
    """One message's standing rating."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    message_id: UUID
    rating: Rating
    rated_at: datetime


class RatedMessageList(CamelModel):
    """The rated messages of one thread."""

    ratings: list[RatedMessage]


class _TurnUsage(CamelModel):
    model_config = ConfigDict(extra="ignore")

    total_tokens: int | None = None
    cost_usd: float | None = None


class RatedTurnMetadata(CamelModel):
    """The part of a message row's metadata a rating report carries."""

    model_config = ConfigDict(extra="ignore")

    trace_id: str | None = None
    usage: _TurnUsage | None = None


class _RatedTurn(CamelModel):
    """The message a rating addresses, read once under the owner check."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    message_id: UUID
    site_id: str
    assistant_id: str
    metadata: RatedTurnMetadata


@asynccontextmanager
async def rating_lock(
    message_id: UUID,
    session_factory: DBSessionFactory,
) -> AsyncIterator[None]:
    """Own one message's rating row and its cases for a whole read-modify-write.

    The lock lives in a session of its own, so each step inside commits on its
    own and a failure between two steps loses no withheld value.
    """
    async with session_factory() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"rating:{message_id}"},
        )
        yield
        await session.commit()


async def _owned_turn(
    session: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
) -> _RatedTurn:
    """The caller's assistant message on the caller's thread, else a 404."""
    conversation: Conversation = await get_visible_conversation(
        ConversationRepository(session), conversation_id, user_id
    )
    message = await session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        ),
    )
    if message is None:
        raise NotFoundError(code=ErrorCode.NOT_FOUND, title="Message not found")
    return _RatedTurn(
        conversation_id=conversation_id,
        message_id=message_id,
        site_id=conversation.site_id,
        assistant_id=conversation.assistant_id,
        metadata=RatedTurnMetadata.model_validate(message.metadata_),
    )


async def _settle(
    session_factory: DBSessionFactory,
    store: MemoryStore,
    view: MessageRatingView,
) -> None:
    """Bring the message's cases into the shape its rating now asks for.

    The withheld values are written before the store changes and trimmed
    after, so no step can lose a case value.
    """
    if not view.case_keys:
        return
    async with session_factory() as session:
        others = await MessageRatingRepository(session).others_for_keys(
            user_id=view.user_id, keys=view.case_keys, excluding=view.message_id
        )
    stored: dict[str, MemoryValue] = {}
    async with memory_store_deadline("the rating's case read"):
        for key in view.case_keys:
            found = await store.get(user_id=view.user_id, kind=CASE_KIND, key=key)
            if found is not None:
                stored[key] = found.value
    held = {case.key: case.value for case in view.withheld_cases}
    moves = settle_cases(
        case_keys=view.case_keys,
        stored=stored,
        withheld=held,
        own=view.rating,
        others=others,
    )
    await _write_withheld(session_factory, view, {**held, **moves.withheld})
    async with memory_store_deadline("the rating's case write"):
        for value, key in moves.put:
            await store.put(user_id=view.user_id, value=value, key=key)
        for key in moves.remove:
            await store.delete(user_id=view.user_id, kind=CASE_KIND, key=key)
    await _write_withheld(session_factory, view, moves.withheld)


async def _write_withheld(
    session_factory: DBSessionFactory,
    view: MessageRatingView,
    withheld: dict[str, MemoryValue],
) -> None:
    async with session_factory() as session:
        await MessageRatingRepository(session).set_withheld(
            view.message_id,
            user_id=view.user_id,
            withheld=[WithheldCase(key=k, value=v) for k, v in withheld.items()],
        )
        await session.commit()


def _report(turn: _RatedTurn, rating: Rating | None) -> None:
    usage = turn.metadata.usage
    record_product_action(
        ProductActionEvent(
            action="message_rated",
            stream_id=str(turn.message_id),
            metadata={
                "rating": rating or "cleared",
                "conversationId": str(turn.conversation_id),
                "messageId": str(turn.message_id),
                "turnTraceId": turn.metadata.trace_id,
                "siteId": turn.site_id,
                "assistantId": turn.assistant_id,
                "totalTokens": None if usage is None else usage.total_tokens,
                "costUsd": None if usage is None else usage.cost_usd,
            },
        ),
    )


async def _follow(
    session_factory: DBSessionFactory,
    store: MemoryStore,
    view: MessageRatingView,
) -> None:
    """Settle the message's cases, then stage or unstage its eval case."""
    await _settle(session_factory, store, view)
    if view.rating == "dislike":
        await stage_disliked_message(session_factory, view.message_id)
    else:
        await unstage_rated_message(session_factory, view.message_id)


async def rate_message(
    *,
    store: MemoryStore,
    user_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    rating: Rating,
    session_factory: DBSessionFactory = async_session_factory,
) -> RatedMessage:
    """Like or dislike one assistant message; the latest rating wins."""
    async with rating_lock(message_id, session_factory):
        async with session_factory() as session:
            turn = await _owned_turn(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
            view = await MessageRatingRepository(session).set_rating(
                message_id=message_id,
                conversation_id=conversation_id,
                user_id=user_id,
                rating=rating,
            )
            await session.commit()
        await _follow(session_factory, store, view)
    _report(turn, rating)
    return RatedMessage.model_validate(view)


async def clear_message_rating(
    *,
    store: MemoryStore,
    user_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    session_factory: DBSessionFactory = async_session_factory,
) -> None:
    """Take the rating back; the message's cases return to their unrated shape.

    A message that was never rated has no row, and a clear writes none.
    """
    async with rating_lock(message_id, session_factory):
        async with session_factory() as session:
            turn = await _owned_turn(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
            repo = MessageRatingRepository(session)
            if await repo.get(message_id, user_id=user_id) is None:
                return
            view = await repo.set_rating(
                message_id=message_id,
                conversation_id=conversation_id,
                user_id=user_id,
                rating=None,
            )
            await session.commit()
        await _follow(session_factory, store, view)
    _report(turn, None)


async def list_message_ratings(
    session: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
) -> RatedMessageList:
    await get_visible_conversation(
        ConversationRepository(session), conversation_id, user_id
    )
    rated = await MessageRatingRepository(session).list_rated(
        conversation_id, user_id=user_id
    )
    return RatedMessageList(
        ratings=[RatedMessage.model_validate(view) for view in rated]
    )


@dataclass(frozen=True)
class TurnMemories:
    """One finished turn's memory candidates, and the message that wrote them."""

    user_id: UUID
    conversation_id: UUID
    message_id: UUID | None
    candidates: Sequence[MemoryCandidate]


async def _write_rated(
    turn: TurnMemories,
    keys: Sequence[str],
    *,
    session_factory: DBSessionFactory,
    store: MemoryStore,
    tombstones: TombstoneRepository,
) -> int:
    async with session_factory() as session:
        repo = MessageRatingRepository(session)
        own = (
            None
            if turn.message_id is None
            else await repo.get(turn.message_id, user_id=turn.user_id)
        )
        others = await repo.others_for_keys(
            user_id=turn.user_id, keys=keys, excluding=turn.message_id
        )
        parts = partition_cases(
            turn.candidates, own=None if own is None else own.rating, others=others
        )
        if turn.message_id is not None:
            await repo.record_turn_cases(
                message_id=turn.message_id,
                conversation_id=turn.conversation_id,
                user_id=turn.user_id,
                keys=keys,
                withheld=[
                    WithheldCase(key=key, value=value) for value, key in parts.withheld
                ],
            )
            await session.commit()
    return await auto_write_memories(
        store=store,
        tombstones=tombstones,
        user_id=turn.user_id,
        candidates=parts.written,
    )


async def write_turn_memories(
    turn: TurnMemories,
    *,
    session_factory: DBSessionFactory,
    store: MemoryStore,
    tombstones: TombstoneRepository,
) -> int:
    """Write a verified turn's memories under the ratings that stand.

    The message's own rating decides its cases first; a case another message
    stands disliked on stays out, and a withheld case is kept on the row.
    Returns how many memories were written.
    """
    keys = [key for value, key in turn.candidates if value.kind == CASE_KIND]
    if not keys:
        return await auto_write_memories(
            store=store,
            tombstones=tombstones,
            user_id=turn.user_id,
            candidates=turn.candidates,
        )
    if turn.message_id is None:
        return await _write_rated(
            turn,
            keys,
            session_factory=session_factory,
            store=store,
            tombstones=tombstones,
        )
    async with rating_lock(turn.message_id, session_factory):
        return await _write_rated(
            turn,
            keys,
            session_factory=session_factory,
            store=store,
            tombstones=tombstones,
        )
