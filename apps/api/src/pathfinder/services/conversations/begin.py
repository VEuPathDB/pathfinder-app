"""Conversation orchestrator: the single entry point for first-action setup.

Every "first action" on a conversation (chat send, slash command, launcher)
calls ``begin_conversation`` first. The endpoint:

1. Idempotently inserts the conversation row (``ON CONFLICT (id) DO NOTHING``)
   so callers don't race when two first actions fire concurrently.
2. Raises ``NotFoundError`` when the row already exists under another user,
   so every caller inherits the ownership check.
3. If the row was newly created and the caller supplied ``seed_text``, kicks
   off async title generation in the background and persists when ready.
4. Returns the (possibly newly-created) conversation.

Downstream endpoints (e.g. ``/chat``) assume the row exists. They do not
lazy-create.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from assistant_core.conversation.authz import get_visible_conversation
from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import calling_application
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationStrategy, ExperimentRow
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.platform.errors import NotFoundError

logger = get_logger(__name__)

DEFAULT_NEW_CONVERSATION_NAME = ""

TitleGenerator = Callable[[str], Awaitable[str]]

_TITLE_TASKS: set[asyncio.Task[None]] = set()


@dataclass
class BeginResult:
    conversation: Conversation
    is_new: bool


async def begin_conversation(
    *,
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    site_id: str,
    assistant_id: str,
    experiment_id: str | None = None,
) -> BeginResult:
    application_id = calling_application()
    if experiment_id is not None:
        experiment = await session.get(ExperimentRow, experiment_id)
        if (
            experiment is None
            or experiment.user_id != user_id
            or experiment.application_id != application_id
        ):
            raise NotFoundError(
                title="Experiment not found",
                detail=f"No experiment {experiment_id!r} owned by the current user.",
            )
    stmt = (
        insert(Conversation)
        .values(
            id=conversation_id,
            user_id=user_id,
            application_id=application_id,
            assistant_id=assistant_id,
            site_id=site_id,
            name=DEFAULT_NEW_CONVERSATION_NAME,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Conversation.id)
    )
    result = await session.execute(stmt)
    inserted_id = result.scalar_one_or_none()
    is_new = inserted_id is not None
    await session.flush()

    repo = ConversationRepository(session)
    if not is_new:
        existing = await get_visible_conversation(repo, conversation_id, user_id)
        return BeginResult(conversation=existing, is_new=False)

    if experiment_id is not None:
        session.add(
            ConversationStrategy(
                conversation_id=conversation_id,
                experiment_id=experiment_id,
            ),
        )
        await session.flush()

    conversation = await repo.get_by_id(conversation_id)
    if conversation is None:
        msg = f"Conversation {conversation_id} not found after upsert"
        raise RuntimeError(msg)

    return BeginResult(conversation=conversation, is_new=True)


def start_title_generation(
    *,
    conversation_id: UUID,
    seed_text: str,
    title_generator: TitleGenerator,
) -> None:
    """Fire-and-forget background title generation for a new conversation.

    Callers inject the (AI) ``title_generator`` so the service layer stays
    free of any AI-layer import.
    """
    if not seed_text.strip():
        return
    task = asyncio.create_task(
        _persist_generated_title(conversation_id, seed_text, title_generator),
    )
    _TITLE_TASKS.add(task)
    task.add_done_callback(_TITLE_TASKS.discard)


async def _persist_generated_title(
    conversation_id: UUID,
    seed_text: str,
    title_generator: TitleGenerator,
) -> None:
    try:
        title = await title_generator(seed_text)
    except Exception:
        logger.exception(
            "begin: title generation failed",
            conversation_id=str(conversation_id),
        )
        return
    if not title:
        return
    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        existing = await repo.get_by_id(conversation_id)
        if existing is None or existing.name:
            return
        await repo.update_conversation(
            conversation_id,
            ConversationUpdate(name=title),
        )
        await session.commit()
