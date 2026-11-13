from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from strategist.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
)

PREVIOUS_REVISION = "2026_11_09_0002"
REVISION = "2026_11_09_0003"


@pytest.fixture
def database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_share_reads"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def test_a_link_says_whether_it_shares_what_was_read(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)

    assert "include_account_reads" in columns(database, "conversation_shares")


def test_the_downgrade_drops_the_column(database: str) -> None:
    command.upgrade(alembic_config(database), REVISION)
    command.downgrade(alembic_config(database), PREVIOUS_REVISION)

    assert "include_account_reads" not in columns(database, "conversation_shares")
