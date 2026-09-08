"""The durable task's phase-picks column, applied to a real database.

A task deferred before the column existed pinned nothing, so it takes the
empty map and its completion turn runs on the configured tier.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).resolve().parents[5] / "alembic.ini"
PREVIOUS_REVISION = "2026_08_30_0001"
REVISION = "2026_08_30_0002"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
EXISTING_TASK_ID = uuid4()


def _psycopg_url(url: str) -> str:
    return (
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
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


def _rows(url: str, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        return connection.execute(query, params).fetchall()


def _columns(url: str, table: str) -> set[str]:
    rows = _rows(
        url,
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    return {row[0] for row in rows}


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'kinases')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO background_tasks "
            "(id, conversation_id, user_id, tool_name, status, args, "
            "estimated_duration_seconds) "
            "VALUES (%s, %s, %s, 'run_eda_compute', 'pending', '{}', 120)",
            (str(EXISTING_TASK_ID), str(CONVERSATION_ID), str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a task that pinned nothing."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_task_phase_overrides"
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    _drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "phase_overrides" not in _columns(seeded_database, "background_tasks")


def test_the_upgrade_gives_an_existing_task_an_empty_map(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    assert "phase_overrides" in _columns(seeded_database, "background_tasks")
    assert _rows(
        seeded_database,
        "SELECT phase_overrides FROM background_tasks WHERE id = %s",
        (str(EXISTING_TASK_ID),),
    ) == [({},)]


def test_a_row_written_without_picks_still_takes_the_empty_map(
    seeded_database: str,
) -> None:
    """The column is NOT NULL, so no task row can leave the picks unreadable."""
    command.upgrade(_config(seeded_database), REVISION)
    fresh = uuid4()

    with psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO background_tasks "
            "(id, conversation_id, user_id, tool_name, status, args, "
            "estimated_duration_seconds) "
            "VALUES (%s, %s, %s, 'run_eda_compute', 'pending', '{}', 120)",
            (str(fresh), str(CONVERSATION_ID), str(USER_ID)),
        )

    assert _rows(
        seeded_database,
        "SELECT phase_overrides FROM background_tasks WHERE id = %s",
        (str(fresh),),
    ) == [({},)]


def test_the_downgrade_removes_the_column_and_keeps_the_task(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    assert "phase_overrides" not in _columns(seeded_database, "background_tasks")
    assert _rows(
        seeded_database,
        "SELECT id FROM background_tasks WHERE id = %s",
        (str(EXISTING_TASK_ID),),
    ) == [(EXISTING_TASK_ID,)]
