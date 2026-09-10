"""The three chains the application's migration entry point runs, on a real database."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import assistant_core.migrate
import psycopg
import pytest
from alembic.autogenerate import (
    compare_metadata,
    produce_migrations,
    render_python_code,
)
from alembic.migration import MigrationContext
from assistant_core.migrate import OWNED_TABLES, VERSION_TABLE
from psycopg.sql import SQL, Identifier
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from pathfinder.persistence.models import Base
from pathfinder.platform.migrations import (
    MCP_VERSION_TABLE,
    include_object,
    upgrade_all,
)

DATABASE_NAME = "pathfinder_test_three_chains"
RUNTIME_BASELINE = "2026_09_09_0001"

# Tables whose models and chain rows disagree on a column type or an index
# name. Each one leaves this application with the next runtime release, so
# each name here dies with its table.
CARRIED_DRIFT = frozenset(
    {
        "background_tasks",
        "task_progress",
        "scratchpad_notes",
        "scratchpad_compactions",
    }
)

Difference = tuple[Any, ...] | list[tuple[Any, ...]]


def _psycopg_url(url: str) -> str:
    return (
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def _revisions(url: str, table: str) -> list[str]:
    query = SQL("SELECT version_num FROM {}").format(Identifier(table))
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(query).fetchall()
    return sorted(row[0] for row in rows)


def _tables(url: str) -> set[str]:
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'",
        ).fetchall()
    return {row[0] for row in rows}


def _runtime_view(connection: Connection) -> list[Difference]:
    """The complement: only the tables the runtime distribution owns."""
    context = MigrationContext.configure(
        connection,
        opts={"include_object": assistant_core.migrate.include_object},
    )
    return list(compare_metadata(context, Base.metadata))


def _revision_body(connection: Connection, exempt: frozenset[str]) -> str:
    """The body alembic writes for a revision generated in this chain."""

    def filtered(
        object_: object,
        name: str | None,
        type_: str,
        reflected: object,
        compare_to: object,
    ) -> bool:
        if type_ == "table" and name in exempt:
            return False
        return include_object(object_, name, type_, reflected, compare_to)

    context = MigrationContext.configure(
        connection,
        opts={"include_object": filtered},
    )
    migrations = produce_migrations(context, Base.metadata)
    rendered = render_python_code(migrations.upgrade_ops, migration_context=context)
    # Alembic wraps the operations in two comments. A revision that carries no
    # operation renders as `pass`.
    lines = [line for line in rendered.splitlines() if not line.strip().startswith("#")]
    return "\n".join(lines).strip()


def _proposed_revision(connection: Connection) -> str:
    return _revision_body(connection, CARRIED_DRIFT)


def _tables_named(body: str) -> set[str]:
    """The tables a rendered revision body names in an operation."""
    return {name for name in Base.metadata.tables if f"'{name}'" in body}


def _operations(differences: list[Difference]) -> list[str]:
    return [str(difference[0]) for difference in differences]


async def _compare[T](
    url: str,
    view: Callable[[Connection], T],
) -> T:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(view)
    finally:
        await engine.dispose()


@pytest.fixture
async def migrated_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> AsyncIterator[str]:
    """A database built only by the application's migration entry point."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"')
        connection.execute(f'CREATE DATABASE "{DATABASE_NAME}"')
    url = (
        make_url(base_url)
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False)
    )

    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_all)
    finally:
        await engine.dispose()

    yield url

    with psycopg.connect(_psycopg_url(base_url), autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"')


def test_the_entry_point_stamps_all_three_version_tables(
    migrated_database: str,
) -> None:
    """Each distribution records its position in a version table of its own."""
    assert _revisions(migrated_database, VERSION_TABLE) == [RUNTIME_BASELINE]
    assert len(_revisions(migrated_database, MCP_VERSION_TABLE)) == 1
    assert len(_revisions(migrated_database, "alembic_version")) == 1


def test_the_entry_point_builds_the_tables_the_runtime_owns(
    migrated_database: str,
) -> None:
    """The four runtime tables stand after one pass of the entry point."""
    assert set(OWNED_TABLES) <= _tables(migrated_database)


async def test_the_two_chains_agree_on_every_runtime_column(
    migrated_database: str,
) -> None:
    """The application's chain built the four tables, so only index names differ."""
    operations = set(_operations(await _compare(migrated_database, _runtime_view)))

    assert operations == {"add_index", "remove_index"}


async def test_autogenerate_proposes_nothing_against_a_migrated_database(
    migrated_database: str,
) -> None:
    """A revision generated on this database carries no operation."""
    assert await _compare(migrated_database, _proposed_revision) == "pass"


@pytest.mark.parametrize("table", sorted(CARRIED_DRIFT))
async def test_a_carried_name_covers_drift_that_leaves_with_its_table(
    migrated_database: str,
    table: str,
) -> None:
    """Each exempt name answers for real drift, so none of them outlives its table."""

    def view(connection: Connection) -> str:
        return _revision_body(connection, CARRIED_DRIFT - {table})

    assert _tables_named(await _compare(migrated_database, view)) == {table}


async def test_the_filter_leaves_a_runtime_table_that_drifts_from_its_model(
    migrated_database: str,
) -> None:
    """A runtime column this chain never adds draws no operation here."""
    before_runtime = _operations(await _compare(migrated_database, _runtime_view))
    with psycopg.connect(_psycopg_url(migrated_database), autocommit=True) as conn:
        conn.execute("ALTER TABLE conversation_events DROP COLUMN turn_id")

    assert "add_column" not in before_runtime
    assert "add_column" in _operations(await _compare(migrated_database, _runtime_view))
    assert await _compare(migrated_database, _proposed_revision) == "pass"
