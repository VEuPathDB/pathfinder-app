"""The name a turn writes on its thread as the last chunk before ``finish``."""

from __future__ import annotations

import asyncio
from uuid import UUID

from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.graph.stream_events import conversation_title_event
from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import StrategyAst

from pathfinder.services.conversations.turns import (
    TitleGenerator,
    name_conversation_if_unnamed,
    rename_if_edits_outdated_it,
)

logger = get_logger(__name__)

TITLE_WAIT_SECONDS = 15.0
"""The longest the turn waits on a title. A slower title is not written."""

__all__ = ["TITLE_WAIT_SECONDS", "write_turn_name"]


async def write_turn_name(
    title_task: asyncio.Task[str] | None,
    conversation_id: UUID,
    writer: ChatWriter,
    *,
    start: StrategyAst | None,
    title_for: TitleGenerator,
) -> None:
    """Write the thread's first title, or the name its edits outdated anew."""
    if title_task is None:
        await _keep_the_name(conversation_id)
    elif await _write_title(title_task, conversation_id, writer):
        return
    try:
        renamed = await asyncio.wait_for(
            rename_if_edits_outdated_it(
                conversation_id, start=start, title_for=title_for
            ),
            TITLE_WAIT_SECONDS,
        )
    except TimeoutError:
        logger.warning(
            "Renaming the strategy exceeded its wait",
            conversation_id=str(conversation_id),
        )
        return
    except Exception:
        logger.exception(
            "Renaming the strategy failed", conversation_id=str(conversation_id)
        )
        return
    if renamed is not None:
        await _write_title_chunk(writer, renamed)


async def _write_title_chunk(writer: ChatWriter, title: str) -> None:
    await writer.write(
        conversation_title_event(title=title).model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )


async def _keep_the_name(conversation_id: UUID) -> None:
    try:
        await name_conversation_if_unnamed(conversation_id, title=None)
    except Exception:
        logger.exception(
            "Keeping the thread name failed", conversation_id=str(conversation_id)
        )


async def _write_title(
    title_task: asyncio.Task[str],
    conversation_id: UUID,
    writer: ChatWriter,
) -> bool:
    """Write the thread's title as the last chunk before the turn finishes.

    Reports whether the title was written.
    """
    try:
        title = await asyncio.wait_for(title_task, TITLE_WAIT_SECONDS)
    except TimeoutError:
        logger.warning(
            "Conversation title generation exceeded its wait",
            conversation_id=str(conversation_id),
        )
        return False
    except Exception:
        logger.exception("Conversation title generation failed")
        return False
    if not title:
        return False
    try:
        named = await name_conversation_if_unnamed(conversation_id, title=title)
    except Exception:
        # The next turn names the thread, so a failed write costs one chunk.
        logger.exception(
            "Naming the thread failed", conversation_id=str(conversation_id)
        )
        return False
    if named:
        await _write_title_chunk(writer, title)
    return named
