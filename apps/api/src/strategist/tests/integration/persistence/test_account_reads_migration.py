from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from strategist.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_11_07_0001"
REVISION = "2026_11_07_0002"


@pytest.fixture
def database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_account_reads"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def test_the_table_holds_one_answer_per_thread(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)

    assert sorted(columns(database, "conversation_account_reads")) == [
        "allowed",
        "conversation_id",
        "updated_at",
    ]


def test_an_account_does_not_always_allow_until_it_says_so(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)
    user_id = str(uuid4())
    with psycopg.connect(psycopg_url(database), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))

    assert rows(
        database, "SELECT account_reads_always FROM users WHERE id = %s", (user_id,)
    ) == [(False,)]


def test_the_downgrade_drops_the_table(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)
    command.downgrade(alembic_config(database), PREVIOUS_REVISION)

    assert columns(database, "conversation_account_reads") == set()
    assert "account_reads_always" not in columns(database, "users")
