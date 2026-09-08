"""The consent column and the staging table, applied to a real database.

Consent defaults on, so an account that predates the notice is opted in and
the notice is what tells them. The staging table's constraint is the linkage
rule: promotion cannot keep the user.
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
PREVIOUS_REVISION = "2026_08_22_0001"
REVISION = "2026_08_23_0001"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()


def _psycopg_url(url: str) -> str:
    return (
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
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


def _stage_one(url: str, staging_id: str) -> None:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, user_id, source_conversation_id, site_id, assistant_id, "
            "content_hash, extract, status) "
            "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, '{}'::jsonb, 'staged')",
            (staging_id, str(USER_ID), str(CONVERSATION_ID), "a" * 64),
        )


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'kinases')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a user with no consent column."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_eval_consent"
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    _drop_database(base_url, name)


def test_the_column_and_the_table_are_absent_before_the_upgrade(
    seeded_database: str,
) -> None:
    assert "eval_data_consent" not in _columns(seeded_database, "users")
    assert _columns(seeded_database, "eval_staged_cases") == set()


def test_the_upgrade_opts_every_existing_account_in(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    rows = _rows(
        seeded_database,
        "SELECT eval_data_consent, eval_notice_seen_at FROM users WHERE id = %s",
        (str(USER_ID),),
    )
    assert rows == [(True, None)]


def test_the_upgrade_creates_the_staging_table(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    columns = _columns(seeded_database, "eval_staged_cases")
    assert "user_id" in columns
    assert "content_hash" in columns
    assert "extract" in columns


def test_the_constraint_refuses_a_promoted_row_that_names_a_user(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    with (
        psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, user_id, source_conversation_id, site_id, assistant_id, "
            "content_hash, extract, status) "
            "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, NULL, 'promoted')",
            (str(uuid4()), str(USER_ID), str(CONVERSATION_ID), "b" * 64),
        )


def test_deleting_the_user_removes_their_staged_rows(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), REVISION)
    staging_id = str(uuid4())
    _stage_one(seeded_database, staging_id)

    with psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute("DELETE FROM users WHERE id = %s", (str(USER_ID),))

    assert (
        _rows(
            seeded_database,
            "SELECT id FROM eval_staged_cases WHERE id = %s",
            (staging_id,),
        )
        == []
    )


def test_the_downgrade_removes_both_and_keeps_the_user(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), REVISION)
    _stage_one(seeded_database, str(uuid4()))

    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    assert "eval_data_consent" not in _columns(seeded_database, "users")
    assert "eval_notice_seen_at" not in _columns(seeded_database, "users")
    assert _columns(seeded_database, "eval_staged_cases") == set()
    assert _rows(
        seeded_database,
        "SELECT id FROM users WHERE id = %s",
        (str(USER_ID),),
    ) == [(str(USER_ID),)]
