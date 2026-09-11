"""Dropping the stored guest token, applied to a real database in both directions."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
)

PREVIOUS_REVISION = "2026_08_19_0001"
COLUMN = "wdk_guest_token"


@pytest.fixture
def database_with_guest_tokens(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database migrated to the revision before the column was dropped."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_guest_token"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def test_the_upgrade_drops_the_stored_guest_token(
    database_with_guest_tokens: str,
) -> None:
    assert COLUMN in columns(database_with_guest_tokens, "users")

    command.upgrade(alembic_config(database_with_guest_tokens), "head")

    assert COLUMN not in columns(database_with_guest_tokens, "users")


def test_the_downgrade_puts_the_column_back(database_with_guest_tokens: str) -> None:
    command.upgrade(alembic_config(database_with_guest_tokens), "head")

    command.downgrade(alembic_config(database_with_guest_tokens), PREVIOUS_REVISION)

    assert COLUMN in columns(database_with_guest_tokens, "users")
