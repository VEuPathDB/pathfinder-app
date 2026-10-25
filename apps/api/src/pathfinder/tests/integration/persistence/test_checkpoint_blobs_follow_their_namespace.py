from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text

from pathfinder.persistence.repositories.checkpoint_rows import (
    copy_checkpoints,
    cut_checkpoints,
)
from pathfinder.platform.config import get_settings

ROOT = ""
CHILD = "lead:subgraph"
VERSION = "00000000000000000000000000000001.0.5"
EARLY = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
LATE = EARLY + timedelta(hours=1)
CUTOFF = EARLY + timedelta(minutes=30)
_BLOBS = text(
    "SELECT checkpoint_ns, channel, version FROM checkpoint_blobs "
    "WHERE thread_id = :thread_id ORDER BY checkpoint_ns",
)


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened


async def _put(
    saver: AsyncPostgresSaver,
    thread_id: str,
    namespace: str,
    at: datetime,
) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["ts"] = at.isoformat()
    checkpoint["channel_values"] = {"findings": [namespace or "root"]}
    checkpoint["channel_versions"] = {"findings": VERSION}
    await saver.aput(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace}},
        checkpoint,
        {},
        checkpoint["channel_versions"],
    )


async def _blobs(thread_id: str) -> list[tuple[str, str, str]]:
    async with db.async_session_factory() as session:
        rows = await session.execute(_BLOBS, {"thread_id": thread_id})
        return [(row.checkpoint_ns, row.channel, row.version) for row in rows]


async def _thread_with_a_late_subgraph(saver: AsyncPostgresSaver) -> str:
    thread_id = str(uuid4())
    await _put(saver, thread_id, ROOT, EARLY)
    await _put(saver, thread_id, CHILD, LATE)
    assert await _blobs(thread_id) == [
        (ROOT, "findings", VERSION),
        (CHILD, "findings", VERSION),
    ]
    return thread_id


async def test_f11_a_branch_copies_no_blob_of_a_namespace_it_did_not_copy(
    saver: AsyncPostgresSaver,
) -> None:
    source = await _thread_with_a_late_subgraph(saver)
    branch = str(uuid4())

    async with db.async_session_factory() as session:
        await copy_checkpoints(
            session,
            source_thread_id=source,
            target_thread_id=branch,
            cutoff=CUTOFF,
        )
        await session.commit()

    assert await _blobs(branch) == [(ROOT, "findings", VERSION)]


async def test_r9_a_revert_drops_a_subgraph_blob_only_the_root_names(
    saver: AsyncPostgresSaver,
) -> None:
    thread_id = await _thread_with_a_late_subgraph(saver)

    async with db.async_session_factory() as session:
        cut = await cut_checkpoints(session, thread_id=thread_id, cutoff=CUTOFF)
        await session.commit()

    assert (cut.checkpoints, cut.blobs) == (1, 1)
    assert await _blobs(thread_id) == [(ROOT, "findings", VERSION)]
