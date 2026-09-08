"""The checkpoint-flush migration, applied to a real database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from langgraph.checkpoint.postgres.base import MIGRATIONS
from psycopg.sql import SQL, Identifier
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).resolve().parents[5] / "alembic.ini"
PREVIOUS_REVISION = "2026_08_19_0002"
THREAD_ID = "8d3b1f6e-0f4a-4d0e-9a7c-6a5f2b1c0d99"
CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def _psycopg_url(url: str) -> str:
    return (
        make_url(url)
        .set(drivername="postgresql")
        .render_as_string(
            hide_password=False,
        )
    )


def _create_database(base_url: str, name: str) -> str:
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
        connection.execute(f'CREATE DATABASE "{name}"')
    return make_url(base_url).set(database=name).render_as_string(hide_password=False)


def _drop_database(base_url: str, name: str) -> None:
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _create_checkpoint_tables(url: str) -> None:
    """Build the checkpoint tables the way the LangGraph saver builds them,
    recording each applied DDL version as the saver's ``setup()`` does."""
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        for version, statement in enumerate(MIGRATIONS):
            if "CONCURRENTLY" in statement:
                continue
            connection.execute(SQL(statement))
            connection.execute(
                "INSERT INTO checkpoint_migrations (v) VALUES (%s)",
                (version,),
            )


def _seed_checkpoint(url: str) -> None:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
            "VALUES (%s, '', %s, %s::jsonb, %s::jsonb)",
            (THREAD_ID, "1efb", '{"v": 1}', '{"turn_id": "abc"}'),
        )
        connection.execute(
            "INSERT INTO checkpoint_blobs "
            "(thread_id, checkpoint_ns, channel, version, type, blob) "
            "VALUES (%s, '', %s, %s, %s, %s)",
            (THREAD_ID, "operational_spec", "1", "msgpack", b"\x80"),
        )
        connection.execute(
            "INSERT INTO checkpoint_writes "
            "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, blob) "
            "VALUES (%s, '', %s, %s, 0, %s, %s)",
            (THREAD_ID, "1efb", "task-1", "verification_digest", b"\x80"),
        )


def _row_counts(url: str) -> dict[str, int]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        return {
            table: connection.execute(
                SQL("SELECT count(*) FROM {}").format(Identifier(table)),
            ).fetchone()[0]
            for table in CHECKPOINT_TABLES
        }


def _ddl_versions(url: str) -> list[int]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT v FROM checkpoint_migrations ORDER BY v",
        ).fetchall()
    return [row[0] for row in rows]


def _table_names(url: str) -> set[str]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'",
        ).fetchall()
    return {row[0] for row in rows}


@pytest.fixture
def checkpointed_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a checkpoint of the old shape."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_checkpoint_flush"
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _create_checkpoint_tables(url)
    _seed_checkpoint(url)
    yield url
    _drop_database(base_url, name)


@pytest.fixture
def checkpointless_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database that has never opened the checkpointer."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_checkpoint_flush_fresh"
    url = _create_database(base_url, name)
    yield url
    _drop_database(base_url, name)


def test_the_upgrade_leaves_no_checkpoint_of_the_old_shape(
    checkpointed_database: str,
) -> None:
    assert _row_counts(checkpointed_database) == dict.fromkeys(CHECKPOINT_TABLES, 1)

    command.upgrade(_config(checkpointed_database), "head")

    assert _row_counts(checkpointed_database) == dict.fromkeys(CHECKPOINT_TABLES, 0)


def test_the_upgrade_keeps_the_checkpointer_ddl_version(
    checkpointed_database: str,
) -> None:
    """Truncating the DDL ledger would make the saver replay its own migrations."""
    before = _ddl_versions(checkpointed_database)
    assert before

    command.upgrade(_config(checkpointed_database), "head")

    assert _ddl_versions(checkpointed_database) == before


def test_a_database_without_checkpoint_tables_upgrades_without_error(
    checkpointless_database: str,
) -> None:
    command.upgrade(_config(checkpointless_database), "head")

    assert CHECKPOINT_TABLES[0] not in _table_names(checkpointless_database)
    assert "conversations" in _table_names(checkpointless_database)


def test_the_downgrade_runs_and_restores_nothing(checkpointed_database: str) -> None:
    command.upgrade(_config(checkpointed_database), "head")

    command.downgrade(_config(checkpointed_database), PREVIOUS_REVISION)

    assert _row_counts(checkpointed_database) == dict.fromkeys(CHECKPOINT_TABLES, 0)
