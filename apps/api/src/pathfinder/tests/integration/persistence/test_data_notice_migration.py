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

PREVIOUS_REVISION = "2026_10_09_0001"
REVISION = "2026_10_09_0002"
USER_ID = uuid4()


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_data_notice"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO users (id, eval_notice_seen_at) VALUES (%s, now())",
            (str(USER_ID),),
        )
    yield url
    drop_database(base_url, name)


def test_an_account_that_saw_the_old_notice_has_seen_no_statement(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    seen = rows(
        seeded_database,
        "SELECT data_notice_seen, eval_data_consent FROM users WHERE id = %s",
        (str(USER_ID),),
    )
    assert seen == [(None, True)]
    assert "eval_notice_seen_at" not in columns(seeded_database, "users")


def test_the_downgrade_brings_back_the_old_marker_unset(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert rows(
        seeded_database,
        "SELECT eval_notice_seen_at FROM users WHERE id = %s",
        (str(USER_ID),),
    ) == [(None,)]
    assert "data_notice_seen" not in columns(seeded_database, "users")
