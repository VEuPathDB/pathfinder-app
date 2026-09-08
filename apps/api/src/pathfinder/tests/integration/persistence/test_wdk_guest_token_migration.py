"""Dropping the stored guest token, applied to a real database in both directions."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).resolve().parents[5] / "alembic.ini"
PREVIOUS_REVISION = "2026_08_19_0001"
COLUMN = "wdk_guest_token"


def _psycopg_url(url: str) -> str:
    return (
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _columns(url: str, table: str) -> set[str]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


@pytest.fixture
def database_with_guest_tokens(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database migrated to the revision before the column was dropped."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_guest_token"
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
        connection.execute(f'CREATE DATABASE "{name}"')
    url = make_url(base_url).set(database=name).render_as_string(hide_password=False)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    yield url
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')


def test_the_upgrade_drops_the_stored_guest_token(
    database_with_guest_tokens: str,
) -> None:
    assert COLUMN in _columns(database_with_guest_tokens, "users")

    command.upgrade(_config(database_with_guest_tokens), "head")

    assert COLUMN not in _columns(database_with_guest_tokens, "users")


def test_the_downgrade_puts_the_column_back(database_with_guest_tokens: str) -> None:
    command.upgrade(_config(database_with_guest_tokens), "head")

    command.downgrade(_config(database_with_guest_tokens), PREVIOUS_REVISION)

    assert COLUMN in _columns(database_with_guest_tokens, "users")
