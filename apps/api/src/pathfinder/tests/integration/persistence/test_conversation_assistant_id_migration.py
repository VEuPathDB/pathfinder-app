"""The assistant-routing column, applied to a real database.

Threads written before assistants were routed have to answer as PathFinder,
so the column is additive and every existing row takes the default.
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
    indexes,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_08_21_0002"
REVISION = "2026_08_22_0001"
USER_ID = uuid4()
EXISTING_ID = uuid4()


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'kinases')",
            (str(EXISTING_ID), str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a conversation with no assistant."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_assistant_routing"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "assistant_id" not in columns(seeded_database, "conversations")


def test_the_upgrade_gives_every_existing_thread_the_default_assistant(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert "assistant_id" in columns(seeded_database, "conversations")
    routed = rows(
        seeded_database,
        "SELECT assistant_id FROM conversations WHERE id = %s",
        (str(EXISTING_ID),),
    )
    assert routed == [("pathfinder",)]


def test_a_row_written_without_an_assistant_still_takes_one(
    seeded_database: str,
) -> None:
    """The column is NOT NULL, so an old writer cannot leave a thread unrouted."""
    command.upgrade(alembic_config(seeded_database), REVISION)
    fresh = uuid4()

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'toxodb', 'later')",
            (str(fresh), str(USER_ID)),
        )

    routed = rows(
        seeded_database,
        "SELECT assistant_id FROM conversations WHERE id = %s",
        (str(fresh),),
    )
    assert routed == [("pathfinder",)]


def test_the_upgrade_indexes_the_column(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert "ix_conversations_assistant_id" in indexes(seeded_database, "conversations")


def test_the_downgrade_removes_the_column_and_its_index(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "assistant_id" not in columns(seeded_database, "conversations")
    assert "ix_conversations_assistant_id" not in indexes(
        seeded_database,
        "conversations",
    )
    assert rows(
        seeded_database,
        "SELECT id FROM conversations WHERE id = %s",
        (str(EXISTING_ID),),
    ) == [(EXISTING_ID,)]
