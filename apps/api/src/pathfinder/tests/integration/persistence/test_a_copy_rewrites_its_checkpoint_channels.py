from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.serde import build_checkpoint_serde
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.persistence.repositories.checkpoint_rows import (
    ChannelRewrite,
    rewrite_channels,
)
from pathfinder.platform.config import get_settings

SERDE = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)
OWNERS = StrategyDomainState(
    original_request="Kinases on chromosome 3",
    control_sets=[NamedControlSet(id="cs-1", name="owner controls")],
)


@pytest.fixture(autouse=True)
async def _checkpoint_tables(patch_app_db_engine: None) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield
    async with db.async_session_factory() as session:
        await session.execute(
            text("TRUNCATE TABLE checkpoints, checkpoint_blobs, checkpoint_writes")
        )
        await session.commit()


async def _seed(thread_id: str, channel: str, value: object) -> None:
    kind, blob = SERDE.dumps_typed(value)
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO checkpoint_blobs "
                "(thread_id, checkpoint_ns, channel, version, type, blob) "
                "VALUES (:thread_id, '', :channel, '1', :type, :blob)"
            ),
            {"thread_id": thread_id, "channel": channel, "type": kind, "blob": blob},
        )
        await session.execute(
            text(
                "INSERT INTO checkpoint_writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, "
                " type, blob, task_path) "
                "VALUES (:thread_id, '', 'c-1', 't', 0, :channel, :type, :blob, '')"
            ),
            {"thread_id": thread_id, "channel": channel, "type": kind, "blob": blob},
        )
        await session.commit()


_READS = {
    "checkpoint_blobs": text(
        "SELECT type, blob FROM checkpoint_blobs "
        "WHERE thread_id = :thread_id AND channel = :channel"
    ),
    "checkpoint_writes": text(
        "SELECT type, blob FROM checkpoint_writes "
        "WHERE thread_id = :thread_id AND channel = :channel"
    ),
}


async def _stored(table: str, thread_id: str, channel: str) -> object:
    async with db.async_session_factory() as session:
        row = (
            await session.execute(
                _READS[table], {"thread_id": thread_id, "channel": channel}
            )
        ).one()
    return SERDE.loads_typed((row.type, bytes(row.blob)))


def _rewrite() -> ChannelRewrite:
    return ChannelRewrite(
        serde=SERDE,
        channels={
            "domain": lambda value: StrategyDomainState.model_validate(
                value
            ).for_another_account()
        },
    )


async def test_the_named_channel_is_rewritten_in_blobs_and_writes() -> None:
    await _seed("copy", "domain", OWNERS)

    async with db.async_session_factory() as session:
        await rewrite_channels(session, thread_id="copy", rewrite=_rewrite())
        await session.commit()

    for table in ("checkpoint_blobs", "checkpoint_writes"):
        stored = StrategyDomainState.model_validate(
            await _stored(table, "copy", "domain")
        )
        assert stored.control_sets == []
        assert stored.original_request == "Kinases on chromosome 3"


async def test_another_thread_keeps_its_channel() -> None:
    await _seed("source", "domain", OWNERS)

    async with db.async_session_factory() as session:
        await rewrite_channels(session, thread_id="copy", rewrite=_rewrite())
        await session.commit()

    stored = StrategyDomainState.model_validate(
        await _stored("checkpoint_blobs", "source", "domain")
    )
    assert stored.control_sets == [NamedControlSet(id="cs-1", name="owner controls")]
