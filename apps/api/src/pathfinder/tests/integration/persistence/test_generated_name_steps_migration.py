"""The marker of a generated strategy name, applied to a real database.

A row written before the column reads null, so no existing name is regenerated.
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

PREVIOUS_REVISION = "2026_09_29_0001"
REVISION = "2026_10_04_0001"
COLUMN = "generated_name_steps"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, application_id, assistant_id, site_id, name) "
            "VALUES (%s, %s, 'pathfinder', 'pathfinder', 'plasmodb', 'Kinases')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversation_strategies "
            "(conversation_id, strategy_ast, imported_saved_strategy_ids) "
            "VALUES (%s, '{}', '[]')",
            (str(CONVERSATION_ID),),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a strategy row."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_generated_name_steps"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def _marker(url: str) -> list[tuple[object, ...]]:
    return rows(
        url,
        "SELECT generated_name_steps FROM conversation_strategies "
        "WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    )


def test_an_existing_name_reads_as_a_person_chose_it(seeded_database: str) -> None:
    assert columns(seeded_database, "conversation_strategies") & {COLUMN} == set()

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _marker(seeded_database) == [(None,)]


def test_the_downgrade_removes_the_column_and_keeps_the_row(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert columns(seeded_database, "conversation_strategies") & {COLUMN} == set()
    assert rows(
        seeded_database,
        "SELECT conversation_id FROM conversation_strategies",
    ) == [(CONVERSATION_ID,)]
