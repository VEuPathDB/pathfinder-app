"""The record of who created a thread's WDK strategy, applied to a real database.

A row written before the column reads false, so a purge leaves the strategy it
names on VEuPathDB.
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

PREVIOUS_REVISION = "2026_09_15_0001"
REVISION = "2026_09_16_0001"
COLUMN = "wdk_strategy_created_here"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
WDK_STRATEGY_ID = 1000001


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, application_id, assistant_id, site_id, name) "
            "VALUES (%s, %s, 'pathfinder', 'pathfinder', 'plasmodb', 'c')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversation_strategies "
            "(conversation_id, wdk_strategy_id, strategy_ast, "
            "imported_saved_strategy_ids) "
            "VALUES (%s, %s, '{}', '[]')",
            (str(CONVERSATION_ID), WDK_STRATEGY_ID),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a strategy of unknown origin."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_wdk_strategy_created_here"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert columns(seeded_database, "conversation_strategies") & {COLUMN} == set()


def test_an_existing_strategy_is_not_claimed_by_the_upgrade(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert rows(
        seeded_database,
        "SELECT wdk_strategy_id, wdk_strategy_created_here "
        "FROM conversation_strategies WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(WDK_STRATEGY_ID, False)]


def test_the_downgrade_removes_the_column_and_keeps_the_strategy(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert columns(seeded_database, "conversation_strategies") & {COLUMN} == set()
    assert rows(
        seeded_database,
        "SELECT wdk_strategy_id FROM conversation_strategies WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(WDK_STRATEGY_ID,)]


def test_the_upgrade_runs_again_after_a_downgrade(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert rows(
        seeded_database,
        "SELECT wdk_strategy_created_here FROM conversation_strategies "
        "WHERE conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(False,)]
