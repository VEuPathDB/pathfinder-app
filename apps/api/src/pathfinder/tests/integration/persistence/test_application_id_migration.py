"""The tenancy migration, applied to a real database in both directions."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from assistant_core.embeddings.embedder import EMBEDDING_DIMENSIONS
from langgraph.store.postgres.base import MIGRATIONS, VECTOR_MIGRATIONS
from psycopg.sql import SQL, Identifier
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).resolve().parents[5] / "alembic.ini"
PREVIOUS_REVISION = "2026_08_09_0001"
# The revision under test. A later one widens the store vector and empties it,
# so the memory rows are read at the revision that moves them.
TENANCY_REVISION = "2026_08_19_0001"
USER_ID = uuid4()
OLD_PREFIX = f"user.{USER_ID}.knowledge"
NEW_PREFIX = f"app.pathfinder.user.{USER_ID}.knowledge"
MEMORY_KEY = "kinome"
TTL_MINUTES = 43200
OWNED_TABLES = (
    "conversations",
    "gene_sets",
    "control_sets",
    "experiments",
    "memory_tombstones",
    "monthly_usage",
)


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


def _create_store_tables(url: str) -> None:
    """Build the store tables the way the LangGraph store builds them."""
    vectors = next(
        migration
        for migration in VECTOR_MIGRATIONS
        if "CREATE TABLE IF NOT EXISTS store_vectors" in migration.sql
    )
    statements = [sql for sql in MIGRATIONS if "CONCURRENTLY" not in sql]
    statements.append(
        vectors.sql % {"vector_type": "vector", "dims": EMBEDDING_DIMENSIONS},
    )
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        for statement in statements:
            connection.execute(SQL(statement))


def _seed_memory(url: str) -> None:
    embedding = "[" + ",".join(["0"] * EMBEDDING_DIMENSIONS) + "]"
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO store (prefix, key, value, expires_at, ttl_minutes) "
            "VALUES (%s, %s, %s::jsonb, now() + interval '30 days', %s)",
            (OLD_PREFIX, MEMORY_KEY, '{"kind": "knowledge"}', TTL_MINUTES),
        )
        connection.execute(
            "INSERT INTO store_vectors (prefix, key, field_name, embedding) "
            "VALUES (%s, %s, %s, %s)",
            (OLD_PREFIX, MEMORY_KEY, "_embed_text", embedding),
        )


def _prefixes(url: str, table: str) -> list[str]:
    query = SQL("SELECT prefix FROM {}").format(Identifier(table))
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(query).fetchall()
    return [row[0] for row in rows]


def _columns(url: str, table: str) -> set[str]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _application_column(url: str, table: str) -> tuple[str, str] | None:
    """Return ``(is_nullable, column_default)`` for the application column."""
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        row = connection.execute(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = 'application_id'",
            (table,),
        ).fetchone()
    if row is None:
        return None
    return (row[0], row[1])


def _unique_constraints(url: str, table: str) -> set[str]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = %s AND constraint_type = 'UNIQUE'",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _indexes(url: str, table: str) -> set[str]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database migrated to the revision before tenancy, holding one memory."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_tenancy_seeded"
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _create_store_tables(url)
    _seed_memory(url)
    yield url
    _drop_database(base_url, name)


@pytest.fixture
def storeless_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database that has never opened the memory store."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_tenancy_fresh"
    url = _create_database(base_url, name)
    yield url
    _drop_database(base_url, name)


def test_the_upgrade_moves_every_memory_under_the_default_application(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), TENANCY_REVISION)

    assert _prefixes(seeded_database, "store") == [NEW_PREFIX]
    assert _prefixes(seeded_database, "store_vectors") == [NEW_PREFIX]


def test_every_owned_table_gains_a_required_column_defaulting_to_pathfinder(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    for table in OWNED_TABLES:
        assert _application_column(seeded_database, table) == (
            "NO",
            "'pathfinder'::character varying",
        ), table


def test_the_upgrade_installs_the_new_indexes_and_unique_keys(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    assert "ix_conversations_user_app_site" in _indexes(
        seeded_database,
        "conversations",
    )
    assert "ix_conversations_user_site" not in _indexes(
        seeded_database, "conversations"
    )
    assert "ix_gene_sets_user_app_site" in _indexes(seeded_database, "gene_sets")
    assert "ix_experiments_user_app" in _indexes(seeded_database, "experiments")
    assert "ix_control_sets_site_app" in _indexes(seeded_database, "control_sets")
    assert "monthly_usage_user_app_period_key" in _unique_constraints(
        seeded_database,
        "monthly_usage",
    )
    assert "uq_tombstones_user_app_kind_hash" in _unique_constraints(
        seeded_database,
        "memory_tombstones",
    )


def test_a_memory_keeps_its_expiry_when_it_moves(seeded_database: str) -> None:
    """Every column of the store row travels, not the ones this revision knew."""
    command.upgrade(_config(seeded_database), "head")

    with psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection:
        row = connection.execute(
            "SELECT ttl_minutes, expires_at IS NOT NULL FROM store WHERE prefix = %s",
            (NEW_PREFIX,),
        ).fetchone()

    assert row == (TTL_MINUTES, True)


def test_the_downgrade_puts_the_memories_and_the_schema_back(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), TENANCY_REVISION)

    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    assert _prefixes(seeded_database, "store") == [OLD_PREFIX]
    assert _prefixes(seeded_database, "store_vectors") == [OLD_PREFIX]
    assert "application_id" not in _columns(seeded_database, "conversations")
    assert "monthly_usage_user_period_key" in _unique_constraints(
        seeded_database,
        "monthly_usage",
    )


def test_a_database_without_store_tables_upgrades_without_error(
    storeless_database: str,
) -> None:
    command.upgrade(_config(storeless_database), "head")

    assert "application_id" in _columns(storeless_database, "conversations")


def _vector_width(url: str, table: str, column: str) -> int:
    """The declared width of a pgvector column."""
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        row = connection.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = %s::regclass AND attname = %s",
            (table, column),
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_the_store_vector_widens_to_the_current_dimension(
    seeded_database: str,
) -> None:
    """A 512-wide vector cannot be read as a 1024-wide one, so the rows go."""
    command.upgrade(_config(seeded_database), "head")

    assert _vector_width(seeded_database, "store_vectors", "embedding") == (
        EMBEDDING_DIMENSIONS
    )
    assert _prefixes(seeded_database, "store_vectors") == []
    assert _prefixes(seeded_database, "store") == [NEW_PREFIX]
