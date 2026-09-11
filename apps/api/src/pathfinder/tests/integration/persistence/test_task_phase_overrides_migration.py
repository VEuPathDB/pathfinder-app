"""The durable task's phase-picks column, applied to a real database.

A task deferred before the column existed pinned nothing, so it takes the
empty map and its completion turn runs on the configured tier.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_08_30_0001"
REVISION = "2026_08_30_0002"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
EXISTING_TASK_ID = uuid4()


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
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
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "phase_overrides" not in columns(seeded_database, "background_tasks")


def test_the_upgrade_gives_an_existing_task_an_empty_map(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert "phase_overrides" in columns(seeded_database, "background_tasks")
    assert rows(
        seeded_database,
        "SELECT phase_overrides FROM background_tasks WHERE id = %s",
        (str(EXISTING_TASK_ID),),
    ) == [({},)]


def test_a_row_written_without_picks_still_takes_the_empty_map(
    seeded_database: str,
) -> None:
    """The column is NOT NULL, so no task row can leave the picks unreadable."""
    command.upgrade(alembic_config(seeded_database), REVISION)
    fresh = uuid4()

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO background_tasks "
            "(id, conversation_id, user_id, tool_name, status, args, "
            "estimated_duration_seconds) "
            "VALUES (%s, %s, %s, 'run_eda_compute', 'pending', '{}', 120)",
            (str(fresh), str(CONVERSATION_ID), str(USER_ID)),
        )

    assert rows(
        seeded_database,
        "SELECT phase_overrides FROM background_tasks WHERE id = %s",
        (str(fresh),),
    ) == [({},)]


def test_the_downgrade_removes_the_column_and_keeps_the_task(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "phase_overrides" not in columns(seeded_database, "background_tasks")
    assert rows(
        seeded_database,
        "SELECT id FROM background_tasks WHERE id = %s",
        (str(EXISTING_TASK_ID),),
    ) == [(EXISTING_TASK_ID,)]
