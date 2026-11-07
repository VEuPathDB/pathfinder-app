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

PREVIOUS_REVISION = "2026_11_06_0001"
REVISION = "2026_11_07_0001"
USER_ID = uuid4()


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_memory_switch"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
    yield url
    drop_database(base_url, name)


def test_an_existing_account_keeps_memory_on(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert rows(
        seeded_database,
        "SELECT memory_enabled FROM users WHERE id = %s",
        (str(USER_ID),),
    ) == [(True,)]


def test_the_downgrade_drops_the_switch(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "memory_enabled" not in columns(seeded_database, "users")
