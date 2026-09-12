"""Stage a chat turn held by a worker whose heartbeat is a chosen age.

The ages come from the settings that decide the window, so a change to the
window cannot leave a staged age on the wrong side of it.
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.chat_turn import defer_chat_turn
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.platform.config import get_settings

TOOL_CALL_ID = "call_search_eda_studies_1"


def dead_window_seconds() -> int:
    """Silence after which a worker counts as dead and loses its jobs."""
    return get_settings().worker_dead_heartbeat_seconds


def fresh_beat_age() -> int:
    """A worker that beat one interval ago."""
    return int(get_settings().worker_heartbeat_interval_seconds)


def starved_age() -> int:
    """A worker that missed many beats and is still inside the window."""
    return dead_window_seconds() - fresh_beat_age()


def dead_age() -> int:
    """Silence far past the window, whatever the window is set to."""
    return dead_window_seconds() * 10


async def stage_chat_turn_job(
    connector: InMemoryConnector,
    *,
    user_id: UUID,
    conversation_id: UUID,
    turn_id: UUID,
    heartbeat_age_seconds: int,
) -> int:
    """Defer a chat turn, put it in ``doing``, and age its worker's heartbeat."""
    payload = ChatTurnPayload(
        body=ChatRequestBody(conversation_id=conversation_id, site_id="plasmodb"),
        user_id=user_id,
        turn_id=turn_id,
        assistant_id="pathfinder",
    )
    job_id = await defer_chat_turn(
        conversation_id=conversation_id,
        payload=payload.model_dump(mode="json", by_alias=True),
    )
    now = datetime.datetime.now(tz=datetime.UTC)
    connector.workers[job_id] = now - datetime.timedelta(seconds=heartbeat_age_seconds)
    connector.jobs[job_id]["status"] = "doing"
    connector.jobs[job_id]["worker_id"] = job_id
    connector.events[job_id].append({"type": "started", "at": now})
    return job_id


async def open_a_tool_call(conversation_id: UUID, turn_id: UUID) -> None:
    """Write a turn whose newest chunk is a tool call with no result."""
    writer = ChatEventWriter(conversation_id=conversation_id, turn_id=turn_id)
    await writer.write({"type": "start", "messageId": str(turn_id)})
    await writer.write(
        {
            "type": "tool-input-start",
            "toolCallId": TOOL_CALL_ID,
            "toolName": "search_eda_studies",
        },
    )
    await writer.write(
        {
            "type": "tool-input-available",
            "toolCallId": TOOL_CALL_ID,
            "toolName": "search_eda_studies",
            "input": {"limit": 5, "query": "malaria transcriptomics"},
        },
    )


async def turn_chunks(conversation_id: UUID) -> list[dict[str, Any]]:
    """Every chunk the conversation logged, oldest first."""
    async with async_session_factory() as session:
        rows = await session.scalars(
            select(ConversationEvent.chunk)
            .where(ConversationEvent.conversation_id == conversation_id)
            .order_by(ConversationEvent.id),
        )
    return list(rows.all())
