from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.conversations.fork_ids import (
    IdMint,
    rewrite_message_ids_in_chunk,
    rewrite_scratchpad_ids_in_chunk,
)


async def copy_conversation_events(
    session: AsyncSession,
    *,
    source_conversation_id: UUID,
    new_conversation_id: UUID,
    cutoff_ts: datetime | None,
    note_id_map: dict[str, str],
    messages: IdMint,
) -> None:
    rows = await session.execute(
        text(
            """
            SELECT id, turn_id, chunk, emitted_at
            FROM conversation_events
            WHERE conversation_id = :src
              AND emitted_at
                  < COALESCE(CAST(:cutoff AS timestamptz), 'infinity'::timestamptz)
            ORDER BY id ASC
            """,
        ),
        {"src": str(source_conversation_id), "cutoff": cutoff_ts},
    )
    inserts: list[dict[str, Any]] = []
    for row in rows.mappings():
        chunk = rewrite_scratchpad_ids_in_chunk(dict(row["chunk"]), note_id_map)
        chunk = rewrite_message_ids_in_chunk(chunk, messages)
        inserts.append(
            {
                "conversation_id": str(new_conversation_id),
                "turn_id": (
                    messages.of(str(row["turn_id"]))
                    if row["turn_id"] is not None
                    else None
                ),
                # The tag names the parent's task row, whose delete cascades.
                # A fork's log outlives every operation on its parent.
                "task_id": None,
                "chunk": chunk,
                # Each copy keeps its source time, because revert cuts on it.
                "emitted_at": row["emitted_at"],
            }
        )
    if not inserts:
        return
    await session.execute(
        text(
            """
            INSERT INTO conversation_events (
                conversation_id, turn_id, task_id, chunk, emitted_at
            )
            VALUES (
                CAST(:conversation_id AS uuid),
                CAST(:turn_id AS uuid),
                CAST(:task_id AS uuid),
                CAST(:chunk AS jsonb),
                CAST(:emitted_at AS timestamptz)
            )
            """,
        ),
        [{**ins, "chunk": json.dumps(ins["chunk"])} for ins in inserts],
    )
