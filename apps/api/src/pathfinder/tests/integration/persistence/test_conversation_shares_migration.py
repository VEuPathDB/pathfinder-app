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
)

PREVIOUS_REVISION = "2026_11_09_0001"
REVISION = "2026_11_09_0002"


@pytest.fixture
def database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_conversation_shares"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def _conversation(database: str) -> str:
    user_id, conversation_id = str(uuid4()), str(uuid4())
    with psycopg.connect(psycopg_url(database), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name, assistant_id) "
            "VALUES (%s, %s, 'plasmodb', 'kinases', 'pathfinder')",
            (conversation_id, user_id),
        )
    return conversation_id


def test_the_table_holds_one_link_per_thread(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)

    assert sorted(columns(database, "conversation_shares")) == [
        "allow_copy",
        "conversation_id",
        "created_at",
        "password_hash",
        "public",
        "token",
        "updated_at",
    ]


def test_a_private_link_must_hold_a_password(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)
    conversation_id = _conversation(database)

    with (
        psycopg.connect(psycopg_url(database), autocommit=True) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            "INSERT INTO conversation_shares "
            "(conversation_id, token, public, password_hash, allow_copy) "
            "VALUES (%s, 'tok', false, NULL, false)",
            (conversation_id,),
        )


def test_the_downgrade_drops_the_table(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)
    command.downgrade(alembic_config(database), PREVIOUS_REVISION)

    assert columns(database, "conversation_shares") == set()
