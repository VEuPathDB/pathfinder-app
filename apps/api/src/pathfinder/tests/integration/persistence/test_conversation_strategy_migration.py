"""The conversation/strategy split migration, applied to a real database."""

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
PREVIOUS_REVISION = "2026_08_21_0001"
USER_ID = uuid4()
BUILT_ID = uuid4()
CLEARED_ID = uuid4()
PLAIN_ID = uuid4()
EXPERIMENT_ID = "exp-1"
AST = '{"root": {"id": "step_a", "searchName": "GenesByTaxon"}}'


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


def _seed_old_shape(url: str) -> None:
    """Three conversations: one built, one cleared, one that never had a plan."""
    with psycopg.connect(_psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO experiments (id, site_id, user_id, name, status, data) "
            "VALUES (%s, %s, %s, 'e', 'pending', '{}'::jsonb)",
            (EXPERIMENT_ID, "plasmodb", str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, site_id, name, record_type, wdk_strategy_id, is_saved, "
            "step_count, strategy_ast, estimated_size, experiment_id, "
            "imported_saved_strategy_ids) "
            "VALUES (%s, %s, 'plasmodb', 'built', 'transcript', 4242, true, 2, "
            "%s::jsonb, 137, %s, '[99]'::jsonb)",
            (str(BUILT_ID), str(USER_ID), AST, EXPERIMENT_ID),
        )
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, site_id, name, strategy_ast, step_count, "
            "imported_saved_strategy_ids) "
            "VALUES (%s, %s, 'plasmodb', 'cleared', 'null'::jsonb, 0, "
            "'[]'::jsonb)",
            (str(CLEARED_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, site_id, name, imported_saved_strategy_ids) "
            "VALUES (%s, %s, 'plasmodb', 'plain', '[]'::jsonb)",
            (str(PLAIN_ID), str(USER_ID)),
        )


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


def _indexes(url: str, table: str) -> set[str]:
    rows = _rows(url, "SELECT indexname FROM pg_indexes WHERE tablename = %s", (table,))
    return {row[0] for row in rows}


def _tables(url: str) -> set[str]:
    rows = _rows(
        url,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'",
    )
    return {row[0] for row in rows}


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding conversations of the old shape."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_conversation_split"
    url = _create_database(base_url, name)
    command.upgrade(_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    _drop_database(base_url, name)


def test_the_upgrade_moves_every_strategy_column_off_the_thread(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    thread_columns = _columns(seeded_database, "conversations")
    assert (
        thread_columns
        & {
            "record_type",
            "wdk_strategy_id",
            "is_saved",
            "step_count",
            "strategy_ast",
            "estimated_size",
            "gene_set_id",
            "gene_set_auto_imported",
            "experiment_id",
            "imported_saved_strategy_ids",
        }
        == set()
    )
    assert {"id", "user_id", "application_id", "site_id", "name"} <= thread_columns


def test_only_a_conversation_that_held_strategy_state_gets_a_side_row(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    ids = {
        str(row[0])
        for row in _rows(
            seeded_database,
            "SELECT conversation_id FROM conversation_strategies",
        )
    }
    assert ids == {str(BUILT_ID)}


def test_the_side_row_carries_the_values_the_thread_held(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    rows = _rows(
        seeded_database,
        "SELECT record_type, wdk_strategy_id, is_saved, step_count, strategy_ast, "
        "estimated_size, experiment_id, imported_saved_strategy_ids "
        "FROM conversation_strategies WHERE conversation_id = %s",
        (str(BUILT_ID),),
    )

    assert rows == [
        (
            "transcript",
            4242,
            True,
            2,
            {"root": {"id": "step_a", "searchName": "GenesByTaxon"}},
            137,
            EXPERIMENT_ID,
            [99],
        ),
    ]


def test_the_unique_wdk_strategy_index_moves_with_the_column(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    assert "ix_conversations_wdk_strategy_id" not in _indexes(
        seeded_database,
        "conversations",
    )
    assert "ix_conversation_strategies_wdk_strategy_id" in _indexes(
        seeded_database,
        "conversation_strategies",
    )


def test_deleting_a_thread_takes_its_side_row_with_it(seeded_database: str) -> None:
    command.upgrade(_config(seeded_database), "head")

    with psycopg.connect(_psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "DELETE FROM conversations WHERE id = %s",
            (str(BUILT_ID),),
        )

    assert _rows(seeded_database, "SELECT count(*) FROM conversation_strategies") == [
        (0,),
    ]


def test_the_downgrade_puts_the_columns_and_the_values_back(
    seeded_database: str,
) -> None:
    command.upgrade(_config(seeded_database), "head")

    command.downgrade(_config(seeded_database), PREVIOUS_REVISION)

    assert _tables(seeded_database) & {"conversation_strategies"} == set()
    assert _rows(
        seeded_database,
        "SELECT record_type, wdk_strategy_id, is_saved, step_count, strategy_ast, "
        "estimated_size, experiment_id, imported_saved_strategy_ids "
        "FROM conversations WHERE id = %s",
        (str(BUILT_ID),),
    ) == [
        (
            "transcript",
            4242,
            True,
            2,
            {"root": {"id": "step_a", "searchName": "GenesByTaxon"}},
            137,
            EXPERIMENT_ID,
            [99],
        ),
    ]
    assert _rows(
        seeded_database,
        "SELECT strategy_ast, wdk_strategy_id FROM conversations WHERE id = %s",
        (str(PLAIN_ID),),
    ) == [({}, None)]
    assert "ix_conversations_wdk_strategy_id" in _indexes(
        seeded_database,
        "conversations",
    )
