from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from langgraph.checkpoint.postgres.base import MIGRATIONS
from psycopg.sql import SQL, Identifier
from testcontainers.community.postgres import PostgresContainer

from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_10_09_0002"
REVISION = "2026_10_12_0001"
USER_ID = uuid4()
REMOVED_ID = uuid4()
KEPT_ID = uuid4()
THREAD_COLUMNS = {
    "conversations": "id",
    "messages": "conversation_id",
    "conversation_events": "conversation_id",
    "checkpoints": "thread_id",
    "checkpoint_blobs": "thread_id",
    "checkpoint_writes": "thread_id",
}


def _create_checkpoint_tables(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        for statement in MIGRATIONS:
            if "CONCURRENTLY" not in statement:
                connection.execute(statement.encode())


def _seed_thread(connection: psycopg.Connection, thread: str, assistant: str) -> None:
    connection.execute(
        "INSERT INTO conversations (id, user_id, site_id, name, assistant_id) "
        "VALUES (%s, %s, 'plasmodb', 'a thread', %s)",
        (thread, str(USER_ID), assistant),
    )
    connection.execute(
        "INSERT INTO messages (id, conversation_id, role) VALUES (%s, %s, 'user')",
        (str(uuid4()), thread),
    )
    connection.execute(
        "INSERT INTO conversation_events (conversation_id, chunk) "
        "VALUES (%s, %s::jsonb)",
        (thread, '{"type": "start"}'),
    )
    connection.execute(
        "INSERT INTO checkpoints "
        "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
        "VALUES (%s, '', '1efb', '{}'::jsonb, '{}'::jsonb)",
        (thread,),
    )
    connection.execute(
        "INSERT INTO checkpoint_blobs "
        "(thread_id, checkpoint_ns, channel, version, type, blob) "
        "VALUES (%s, '', 'messages', '1', 'msgpack', %s)",
        (thread, b"\x80"),
    )
    connection.execute(
        "INSERT INTO checkpoint_writes "
        "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, blob) "
        "VALUES (%s, '', '1efb', 'task-1', 0, 'messages', %s)",
        (thread, b"\x80"),
    )


def _seed(url: str) -> None:
    _create_checkpoint_tables(url)
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        _seed_thread(connection, str(REMOVED_ID), "site_help")
        _seed_thread(connection, str(KEPT_ID), "pathfinder")


def _threads_in(url: str, table: str) -> list[str]:
    found = rows(
        url,
        SQL("SELECT DISTINCT {}::text FROM {}").format(
            Identifier(THREAD_COLUMNS[table]), Identifier(table)
        ),
    )
    return [row[0] for row in found]


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_removed_assistant_threads"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed(url)
    yield url
    drop_database(base_url, name)


@pytest.fixture
def checkpointless_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_removed_assistant_fresh"
    url = create_database(base_url, name)
    yield url
    drop_database(base_url, name)


@pytest.mark.parametrize("table", THREAD_COLUMNS)
def test_the_upgrade_keeps_only_the_threads_of_an_installed_assistant(
    seeded_database: str, table: str
) -> None:
    assert sorted(_threads_in(seeded_database, table)) == sorted(
        [str(REMOVED_ID), str(KEPT_ID)]
    )

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _threads_in(seeded_database, table) == [str(KEPT_ID)]


def test_the_upgrade_runs_where_no_checkpointer_has_opened(
    checkpointless_database: str,
) -> None:
    command.upgrade(alembic_config(checkpointless_database), REVISION)

    assert rows(checkpointless_database, "SELECT count(*) FROM conversations") == [(0,)]


def test_the_downgrade_restores_nothing_and_succeeds(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert _threads_in(seeded_database, "conversations") == [str(KEPT_ID)]
