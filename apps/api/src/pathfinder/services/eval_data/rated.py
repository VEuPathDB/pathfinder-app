"""A disliked message becomes one staged eval case: the thread cut at that message."""

from __future__ import annotations

from uuid import UUID

from assistant_core.persistence.models import Conversation, ConversationEvent, Message
from assistant_core.platform.db import DBSessionFactory
from assistant_core.platform.logging import get_logger
from pydantic import ValidationError
from sqlalchemy import func, select

from pathfinder.evals.extract import EvalExtract
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.services.eval_data.extraction import (
    extract_from_rows,
    extracted_strategy,
    failed_redaction,
    logged_chunks,
)
from pathfinder.services.strategies.revision_ops import revision_at_message

logger = get_logger(__name__)

__all__ = ["stage_disliked_message", "unstage_rated_message"]


async def _extract_through(
    session_factory: DBSessionFactory,
    message_id: UUID,
) -> tuple[Conversation, EvalExtract] | None:
    """The thread up to the end of the message, with the strategy in force then.

    None when the user has not consented or the log holds nothing of it.
    """
    async with session_factory() as session:
        message = await session.get(Message, message_id)
        if message is None:
            return None
        conversation = await session.get(Conversation, message.conversation_id)
        if conversation is None:
            return None
        consent = await session.scalar(
            select(User.eval_data_consent).where(User.id == conversation.user_id)
        )
        through = await session.scalar(
            select(func.max(ConversationEvent.id)).where(
                ConversationEvent.conversation_id == conversation.id,
                ConversationEvent.turn_id == message.id,
            )
        )
        if consent is not True or through is None:
            return None
        rows = await logged_chunks(session, conversation.id, through=through)
        revision = await revision_at_message(session, message=message)
    extract = extract_from_rows(
        site_id=conversation.site_id,
        assistant_id=conversation.assistant_id,
        rows=rows,
        strategy=(
            None
            if revision is None
            else extracted_strategy(
                record_type=revision.record_type,
                step_count=revision.step_count,
                strategy_ast=revision.strategy_ast,
            )
        ),
    )
    return None if extract is None else (conversation, extract)


async def stage_disliked_message(
    session_factory: DBSessionFactory,
    message_id: UUID,
) -> UUID | None:
    """Queue the thread through the disliked message, once per message.

    None when the user has not consented, the extract fails redaction, or the
    content is already known.
    """
    try:
        found = await _extract_through(session_factory, message_id)
    except ValidationError as exc:
        if not failed_redaction(exc):
            raise
        logger.warning("a disliked message failed redaction and was not staged")
        return None
    if found is None:
        return None
    conversation, extract = found
    return await EvalStagingRepository(session_factory=session_factory).stage(
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        extract=extract,
        rated_message_id=message_id,
    )


async def unstage_rated_message(
    session_factory: DBSessionFactory, message_id: UUID
) -> None:
    """Take a message's staged case off the queue. A promoted case stays."""
    await EvalStagingRepository(session_factory=session_factory).unstage_rated(
        message_id
    )
