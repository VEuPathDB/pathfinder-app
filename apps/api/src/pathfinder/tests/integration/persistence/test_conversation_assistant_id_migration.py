"""The assistant-routing column, applied to a real database.

Threads written before assistants were routed have to answer as PathFinder,
so the column is additive and every existing row takes the default.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).resolve().parents[5] / "alembic.ini"
PREVIOUS_REVISION = "2026_08_21_0002"
REVISION = "2026_08_22_0001"
USER_ID = uuid4()
EXISTING_ID = uuid4()


def _psycopg_url(url: str) -> str:
    return (
        make_url(url)
        .set(drivername="postgresql")
        .render_as_string(
            hide_password=False,
        )
    )


def _create_database(base_url: str, name: str) -> str:
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
        connection.execute(f'CREATE DATABASE "{name}"')
    return make_url(base_url).set(database=name).render_as_string(hide_password=False)


def _drop_database(base_url: str, name: str) -> None:
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _rows(url: str, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        return connection.execute(query, params).fetchall()


def _columns(url: str, table: str) -> set[str]:
    rows = _rows(
        url,
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    return {row[0] for row in rows}


def _indexes(url: str, table: str) -> set[str]:
    rows = _rows(url, "SELECT indexname FROM pg_indexes WHERE tablename = %s", (table,))
    return {row[0] for row in rows}


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
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
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    _drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "assistant_id" not in _columns(seeded_database, "conversations")


def test_the_upgrade_gives_every_existing_thread_the_default_assistant(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    assert "assistant_id" in _columns(seeded_database, "conversations")
    rows = _rows(
        seeded_database,
        "SELECT assistant_id FROM conversations WHERE id = %s",
        (str(EXISTING_ID),),
    )
    assert rows == [("pathfinder",)]


def test_a_row_written_without_an_assistant_still_takes_one(
    seeded_database: str,
) -> None:
    """The column is NOT NULL, so an old writer cannot leave a thread unrouted."""
    command.upgrade(_config(seeded_database), REVISION)
    fresh = uuid4()

    with psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'toxodb', 'later')",
            (str(fresh), str(USER_ID)),
        )

    rows = _rows(
        seeded_database,
        "SELECT assistant_id FROM conversations WHERE id = %s",
        (str(fresh),),
    )
    assert rows == [("pathfinder",)]


def test_the_upgrade_indexes_the_column(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    assert "ix_conversations_assistant_id" in _indexes(seeded_database, "conversations")


def test_the_downgrade_removes_the_column_and_its_index(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    assert "assistant_id" not in _columns(seeded_database, "conversations")
    assert "ix_conversations_assistant_id" not in _indexes(
        seeded_database,
        "conversations",
    )
    assert _rows(
        seeded_database,
        "SELECT id FROM conversations WHERE id = %s",
        (str(EXISTING_ID),),
    ) == [(EXISTING_ID,)]
