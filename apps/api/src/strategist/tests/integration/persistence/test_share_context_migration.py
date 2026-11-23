from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_11_23_0001"
REVISION = "2026_11_24_0001"


@pytest.fixture
def database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "strategist_test_share_context"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def _share(database: str, token: str) -> None:
    user_id, conversation_id = str(uuid4()), str(uuid4())
    with psycopg.connect(psycopg_url(database), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name, assistant_id) "
            "VALUES (%s, %s, 'plasmodb', 'kinases', %s)",
            (conversation_id, user_id, STRATEGIST_ASSISTANT_ID),
        )
        connection.execute(
            "INSERT INTO conversation_shares "
            "(conversation_id, token, public, password_hash, allow_copy) "
            "VALUES (%s, %s, true, NULL, false)",
            (conversation_id, token),
        )


def _include_context_of(database: str, token: str) -> list[tuple[object, ...]]:
    return rows(
        database,
        "SELECT include_context FROM conversation_shares WHERE token = %s",
        (token,),
    )


def test_a_link_made_before_keeps_the_context_out(database: str) -> None:
    _share(database, "tok-before")

    command.upgrade(alembic_config(database), REVISION)

    assert _include_context_of(database, "tok-before") == [(False,)]


def test_a_link_made_after_carries_the_context(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)

    _share(database, "tok-after")

    assert _include_context_of(database, "tok-after") == [(True,)]


def test_the_downgrade_drops_the_column(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)
    command.downgrade(alembic_config(database), PREVIOUS_REVISION)

    assert "include_context" not in columns(database, "conversation_shares")
