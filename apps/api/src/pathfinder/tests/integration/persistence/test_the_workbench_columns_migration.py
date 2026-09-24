"""The columns only the workbench wrote, dropped from a real database.

The rows that carried them stay, and the downgrade restores each column empty,
with its index and its foreign key.
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

PREVIOUS_REVISION = "2026_09_24_0002"
REVISION = "2026_09_24_0003"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
SET_ID = "gs-gametocyte-union"
EXPERIMENT_ID = "exp-gametocyte-panel"
GENE_SET_COLUMNS = {"parent_set_ids", "operation", "enrichment_results"}
EXPERIMENT_COLUMNS = {"batch_id", "benchmark_id", "gene_set_id"}
EXPERIMENT_INDEXES = {
    "ix_experiments_batch_id",
    "ix_experiments_benchmark_id",
    "ix_experiments_gene_set_id",
}
_EXPERIMENT_FOREIGN_KEY = (
    "SELECT confrelid::regclass::text, confdeltype FROM pg_constraint "
    "WHERE conrelid = 'conversation_strategies'::regclass AND contype = 'f' "
    "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute "
    "WHERE attrelid = 'conversation_strategies'::regclass "
    "AND attname = 'experiment_id')]"
)


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO gene_sets "
            "(id, user_id, site_id, name, gene_ids, source, parent_set_ids, "
            "operation, step_count, enrichment_results, application_id) "
            "VALUES (%s, %s, 'plasmodb', 'gametocyte union', "
            "'[\"PF3D7_1133400\"]', 'derived', '[\"gs-a\", \"gs-b\"]', 'union', "
            "1, '[{\"analysisType\": \"go_process\"}]', 'pathfinder')",
            (SET_ID, str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO experiments "
            "(id, site_id, user_id, application_id, name, status, data, "
            "batch_id, benchmark_id, gene_set_id) "
            "VALUES (%s, 'plasmodb', %s, 'pathfinder', 'gametocyte panel', "
            "'completed', '{}', 'batch-1', 'bench-1', %s)",
            (EXPERIMENT_ID, str(USER_ID), SET_ID),
        )
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, application_id, assistant_id, site_id, name) "
            "VALUES (%s, %s, 'pathfinder', 'pathfinder', 'plasmodb', 'c')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversation_strategies "
            "(conversation_id, strategy_ast, imported_saved_strategy_ids, "
            "experiment_id) VALUES (%s, '{}', '[]', %s)",
            (str(CONVERSATION_ID), EXPERIMENT_ID),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, whose rows fill every workbench column."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_the_workbench_columns"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_upgrade_drops_every_workbench_column(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert columns(seeded_database, "gene_sets") & GENE_SET_COLUMNS == set()
    assert columns(seeded_database, "experiments") & EXPERIMENT_COLUMNS == set()
    assert "experiment_id" not in columns(seeded_database, "conversation_strategies")
    assert indexes(seeded_database, "experiments") & EXPERIMENT_INDEXES == set()


def test_the_upgrade_keeps_the_rows_that_carried_them(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert rows(seeded_database, "SELECT id, source FROM gene_sets") == [
        (SET_ID, "derived")
    ]
    assert rows(seeded_database, "SELECT id, status FROM experiments") == [
        (EXPERIMENT_ID, "completed")
    ]
    assert rows(
        seeded_database, "SELECT conversation_id FROM conversation_strategies"
    ) == [(CONVERSATION_ID,)]


def test_the_downgrade_restores_each_column_empty(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert rows(
        seeded_database,
        "SELECT parent_set_ids::text, operation, enrichment_results::text "
        "FROM gene_sets",
    ) == [("[]", None, "[]")]
    assert rows(
        seeded_database,
        "SELECT batch_id, benchmark_id, gene_set_id FROM experiments",
    ) == [(None, None, None)]
    assert rows(
        seeded_database, "SELECT experiment_id FROM conversation_strategies"
    ) == [(None,)]
    assert indexes(seeded_database, "experiments") >= EXPERIMENT_INDEXES
    assert rows(seeded_database, _EXPERIMENT_FOREIGN_KEY) == [("experiments", "n")]


def test_the_upgrade_runs_again_after_a_downgrade(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert columns(seeded_database, "gene_sets") & GENE_SET_COLUMNS == set()
    assert columns(seeded_database, "experiments") & EXPERIMENT_COLUMNS == set()
