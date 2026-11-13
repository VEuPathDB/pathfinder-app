from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.serde import build_checkpoint_serde
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, empty_checkpoint
from testcontainers.community.postgres import PostgresContainer

from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.assistants.strategist_spec import STRATEGIST_CHECKPOINT_TYPES
from strategist.tests._support.checkpoint_state import domain_state, populated_state
from strategist.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_11_10_0001"
REVISION = "2026_11_13_0001"
THREAD_ID = "5f0c2c9e-6c3a-4d55-9e57-1b0b3e0d7a11"
TASK_ID = "task-1"
_SERDE = build_checkpoint_serde(STRATEGIST_CHECKPOINT_TYPES)
_RECORDED = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "checkpoints"
    / "channels-under-the-pathfinder-package.json"
)


def _recorded() -> dict[str, bytes]:
    stored: dict[str, str] = json.loads(_RECORDED.read_text())
    return {channel: base64.b64decode(blob) for channel, blob in stored.items()}


def _config() -> RunnableConfig:
    return {"configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}}


async def _write_the_thread(url: str) -> None:
    state = populated_state()
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {
        name: getattr(state, name) for name in PipelineState.model_fields
    }
    versions: ChannelVersions = dict.fromkeys(checkpoint["channel_values"], 1)
    checkpoint["channel_versions"] = dict(versions)
    async with lifespan_checkpointer(
        url, checkpoint_types=STRATEGIST_CHECKPOINT_TYPES
    ) as saver:
        written = await saver.aput(
            _config(), checkpoint, {"source": "loop", "step": 1}, versions
        )
        await saver.aput_writes(written, [("domain", domain_state())], TASK_ID)


def _store_the_old_package_bytes(url: str) -> None:
    recorded = _recorded()
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        for channel, blob in recorded.items():
            connection.execute(
                "UPDATE checkpoint_blobs SET blob = %s "
                "WHERE thread_id = %s AND channel = %s",
                (blob, THREAD_ID, channel),
            )
        connection.execute(
            "UPDATE checkpoint_writes SET blob = %s WHERE thread_id = %s",
            (recorded["domain"], THREAD_ID),
        )


async def _read_the_thread(url: str) -> tuple[dict[str, Any], list[Any]]:
    async with lifespan_checkpointer(
        url, checkpoint_types=STRATEGIST_CHECKPOINT_TYPES
    ) as saver:
        stored = await saver.aget_tuple(_config())
    assert stored is not None
    return dict(stored.checkpoint["channel_values"]), [
        value for _, _, value in stored.pending_writes or []
    ]


def _blobs(url: str) -> dict[str, bytes]:
    found = rows(
        url,
        "SELECT channel, blob FROM checkpoint_blobs WHERE thread_id = %s",
        (THREAD_ID,),
    )
    return {channel: bytes(blob) for channel, blob in found}


@pytest.fixture
def old_thread_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_package_rename"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    asyncio.run(_write_the_thread(url))
    _store_the_old_package_bytes(url)
    yield url
    drop_database(base_url, name)


@pytest.fixture
def checkpointless_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_package_rename_fresh"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def test_a_thread_the_old_package_wrote_does_not_load_before_the_upgrade(
    old_thread_database: str,
) -> None:
    channels, writes = asyncio.run(_read_the_thread(old_thread_database))

    assert type(channels["domain"]) is dict
    assert type(writes[0]) is dict


def test_a_thread_the_old_package_wrote_loads_whole_after_the_upgrade(
    old_thread_database: str,
) -> None:
    command.upgrade(alembic_config(old_thread_database), REVISION)

    channels, writes = asyncio.run(_read_the_thread(old_thread_database))

    assert type(channels["domain"]) is StrategyDomainState
    assert PipelineState.model_validate(channels) == populated_state()
    assert writes == [domain_state()]


def test_the_downgrade_restores_the_bytes_the_old_package_wrote(
    old_thread_database: str,
) -> None:
    before = _blobs(old_thread_database)

    command.upgrade(alembic_config(old_thread_database), REVISION)
    assert _blobs(old_thread_database) != before
    command.downgrade(alembic_config(old_thread_database), PREVIOUS_REVISION)

    assert _blobs(old_thread_database) == before


def test_the_upgrade_renames_more_rows_than_one_batch_holds(
    old_thread_database: str,
) -> None:
    old = _recorded()["domain"]
    with psycopg.connect(psycopg_url(old_thread_database), autocommit=True) as db:
        for version in range(450):
            db.execute(
                "INSERT INTO checkpoint_blobs "
                "(thread_id, checkpoint_ns, channel, version, type, blob) "
                "VALUES ('another-thread', '', 'domain', %s, 'msgpack', %s)",
                (f"{version:04}", old),
            )

    command.upgrade(alembic_config(old_thread_database), REVISION)

    renamed = rows(
        old_thread_database,
        "SELECT DISTINCT blob FROM checkpoint_blobs WHERE thread_id = 'another-thread'",
    )
    assert [bytes(blob) for (blob,) in renamed] == [
        _SERDE.dumps_typed(domain_state())[1]
    ]


def test_the_upgrade_runs_where_no_checkpointer_has_opened(
    checkpointless_database: str,
) -> None:
    command.upgrade(alembic_config(checkpointless_database), REVISION)

    assert rows(checkpointless_database, "SELECT version_num FROM alembic_version") == [
        (REVISION,)
    ]
