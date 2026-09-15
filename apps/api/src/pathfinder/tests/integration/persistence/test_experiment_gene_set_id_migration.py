"""The experiment's gene-set pointer, applied to a real database.

An experiment that ran before the column keeps an empty pointer, and the
downgrade leaves the experiment itself untouched.
"""

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
    indexes,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_09_13_0001"
REVISION = "2026_09_15_0001"
USER_ID = uuid4()
EXISTING_EXPERIMENT_ID = "exp-before-the-column"
SET_ID = "gs-gametocyte-secreted"


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO experiments "
            "(id, site_id, user_id, application_id, name, status, data) "
            "VALUES (%s, 'plasmodb', %s, 'pathfinder', "
            "'gametocyte secreted (evaluation)', 'completed', '{}')",
            (EXISTING_EXPERIMENT_ID, str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding an experiment with no set."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_experiment_gene_set_id"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "gene_set_id" not in columns(seeded_database, "experiments")


def test_the_upgrade_keeps_the_experiment_and_leaves_its_pointer_empty(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert "gene_set_id" in columns(seeded_database, "experiments")
    assert rows(
        seeded_database,
        "SELECT name, status, gene_set_id FROM experiments WHERE id = %s",
        (EXISTING_EXPERIMENT_ID,),
    ) == [("gametocyte secreted (evaluation)", "completed", None)]


def test_the_upgrade_indexes_the_pointer(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert "ix_experiments_gene_set_id" in indexes(seeded_database, "experiments")


def test_an_evaluation_records_the_set_it_ran_against(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "UPDATE experiments SET gene_set_id = %s WHERE id = %s",
            (SET_ID, EXISTING_EXPERIMENT_ID),
        )

    assert rows(
        seeded_database,
        "SELECT gene_set_id FROM experiments WHERE id = %s",
        (EXISTING_EXPERIMENT_ID,),
    ) == [(SET_ID,)]


def test_the_downgrade_removes_the_column_and_keeps_the_experiment(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "gene_set_id" not in columns(seeded_database, "experiments")
    assert rows(
        seeded_database,
        "SELECT id FROM experiments WHERE id = %s",
        (EXISTING_EXPERIMENT_ID,),
    ) == [(EXISTING_EXPERIMENT_ID,)]


def test_the_upgrade_runs_again_after_a_downgrade(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert "gene_set_id" in columns(seeded_database, "experiments")
