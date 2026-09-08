"""The gene set's published-dataset pointer, applied to a real database.

A set that was never published keeps an empty pointer, and the downgrade
leaves the set itself untouched.
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
PREVIOUS_REVISION = "2026_08_31_0001"
REVISION = "2026_09_05_0001"
USER_ID = uuid4()
EXISTING_SET_ID = "gs-before-the-column"


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


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO gene_sets "
            "(id, user_id, site_id, name, gene_ids, source, parent_set_ids, "
            "step_count, enrichment_results, application_id) "
            "VALUES (%s, %s, 'plasmodb', 'kinases', '[\"PF3D7_1133400\"]', "
            "'paste', '[]', 1, '[]', 'pathfinder')",
            (EXISTING_SET_ID, str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a set nobody published."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_gene_set_vdi_id"
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    _drop_database(base_url, name)


def test_the_column_is_absent_before_the_upgrade(seeded_database: str) -> None:
    assert "vdi_id" not in _columns(seeded_database, "gene_sets")


def test_the_upgrade_leaves_an_unpublished_set_with_no_pointer(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    assert "vdi_id" in _columns(seeded_database, "gene_sets")
    assert _rows(
        seeded_database,
        "SELECT vdi_id FROM gene_sets WHERE id = %s",
        (EXISTING_SET_ID,),
    ) == [(None,)]


def test_a_published_set_keeps_the_identifier_the_service_issued(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    with psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "UPDATE gene_sets SET vdi_id = %s WHERE id = %s",
            ("soV5JEQEcF00p", EXISTING_SET_ID),
        )

    assert _rows(
        seeded_database,
        "SELECT vdi_id FROM gene_sets WHERE id = %s",
        (EXISTING_SET_ID,),
    ) == [("soV5JEQEcF00p",)]


def test_the_downgrade_removes_the_column_and_keeps_the_set(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), REVISION)

    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    assert "vdi_id" not in _columns(seeded_database, "gene_sets")
    assert _rows(
        seeded_database,
        "SELECT id FROM gene_sets WHERE id = %s",
        (EXISTING_SET_ID,),
    ) == [(EXISTING_SET_ID,)]


def test_the_upgrade_runs_again_after_a_downgrade(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), REVISION)
    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    command.upgrade(_config(seeded_database), REVISION)

    assert "vdi_id" in _columns(seeded_database, "gene_sets")
