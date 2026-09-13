"""The preview flag on a thread's analysis, applied to a real database.

An analysis bound before the column exists starts uncounted, so the export
still waits for a preview.
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

PREVIOUS_REVISION = "2026_09_05_0001"
REVISION = "2026_09_13_0001"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
ANALYSIS_ID = "4XlEvvr"


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'heat shock')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversation_analyses "
            "(conversation_id, site_id, dataset_id, analysis_id, revision) "
            "VALUES (%s, 'plasmodb', 'DS_e973eadd57', %s, 3)",
            (str(CONVERSATION_ID), ANALYSIS_ID),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a thread with an open analysis."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_analysis_subset_preview"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "subset_previewed" not in columns(seeded_database, "conversation_analyses")


def test_an_analysis_bound_before_the_column_counts_as_unpreviewed(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert rows(
        seeded_database,
        "SELECT subset_previewed, revision FROM conversation_analyses "
        "WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(False, 3)]


def test_the_preview_is_recorded_on_the_row(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "UPDATE conversation_analyses SET subset_previewed = true "
            "WHERE conversation_id = %s",
            (str(CONVERSATION_ID),),
        )

    assert rows(
        seeded_database,
        "SELECT subset_previewed FROM conversation_analyses WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(True,)]


def test_the_downgrade_removes_the_column_and_keeps_the_binding(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "subset_previewed" not in columns(seeded_database, "conversation_analyses")
    assert rows(
        seeded_database,
        "SELECT analysis_id FROM conversation_analyses WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(ANALYSIS_ID,)]
