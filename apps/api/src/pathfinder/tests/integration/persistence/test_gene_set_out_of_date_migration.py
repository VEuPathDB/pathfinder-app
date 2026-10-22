from __future__ import annotations

import json
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

PREVIOUS_REVISION = "2026_10_21_0001"
REVISION = "2026_10_22_0001"
USER_ID = uuid4()
SET_ID = "gs-before-the-mark"
_ABOVE = {"kind": "above_the_cap", "count": 523_795, "cap": 10_000}


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO gene_sets (id, user_id, application_id, site_id, name, "
            "gene_ids, source, step_count, record_type) "
            "VALUES (%s, %s, 'pathfinder', 'orthomcl', 'singletons', %s, "
            "'strategy', 2, 'sequence')",
            (SET_ID, str(USER_ID), json.dumps(["PF3D7_0103400.1-p1"])),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_gene_set_out_of_date"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def _marks(url: str) -> list[tuple[object, ...]]:
    return rows(url, "SELECT id, out_of_date FROM gene_sets", ())


def test_the_upgrade_leaves_a_set_unmarked(seeded_database: str) -> None:
    assert "out_of_date" not in columns(seeded_database, "gene_sets")

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _marks(seeded_database) == [(SET_ID, None)]


def test_a_mark_is_written_and_read_back(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "UPDATE gene_sets SET out_of_date = %s WHERE id = %s",
            (json.dumps(_ABOVE), SET_ID),
        )

    assert _marks(seeded_database) == [(SET_ID, _ABOVE)]


def test_the_downgrade_drops_the_column_and_keeps_the_set(
    seeded_database: str,
) -> None:
    before = columns(seeded_database, "gene_sets")
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert (
        columns(seeded_database, "gene_sets"),
        rows(seeded_database, "SELECT id FROM gene_sets", ()),
    ) == (before, [(SET_ID,)])


def test_the_upgrade_runs_again_after_a_downgrade(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _marks(seeded_database) == [(SET_ID, None)]
