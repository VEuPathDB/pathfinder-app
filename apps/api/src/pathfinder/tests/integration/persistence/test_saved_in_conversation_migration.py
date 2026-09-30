"""The thread a gene set or a control set was saved in, applied to a real database.

A set saved before the column names no thread, and a set outlives the thread
it was saved in.
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
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_09_24_0004"
REVISION = "2026_09_28_0001"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
CONTROL_SET_ID = uuid4()
GENE_SET_ID = "gs-before-the-column"
TABLES = ("gene_sets", "control_sets")


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'vaccine candidates')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO gene_sets "
            "(id, user_id, site_id, name, gene_ids, source, step_count, "
            "application_id) "
            "VALUES (%s, %s, 'plasmodb', 'kinases', '[\"PF3D7_1133400\"]', "
            "'paste', 1, 'pathfinder')",
            (GENE_SET_ID, str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO control_sets "
            "(id, user_id, name, site_id, record_type, positive_ids, negative_ids, "
            "tags, version, is_public, application_id) "
            "VALUES (%s, %s, 'antigens', 'plasmodb', 'transcript', "
            "'[\"PF3D7_0304600\"]', '[]', '[]', 1, false, 'pathfinder')",
            (str(CONTROL_SET_ID), str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding one set of each kind."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_saved_in_conversation"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def _saved_in(url: str) -> list[tuple[object, ...]]:
    return rows(
        url,
        "SELECT conversation_id FROM gene_sets WHERE id = %s "
        "UNION ALL SELECT conversation_id FROM control_sets WHERE id = %s",
        (GENE_SET_ID, str(CONTROL_SET_ID)),
    )


def test_the_upgrade_leaves_an_older_set_in_no_thread(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert all("conversation_id" in columns(seeded_database, t) for t in TABLES)
    assert _saved_in(seeded_database) == [(None,), (None,)]


def test_a_set_outlives_the_thread_it_was_saved_in(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "UPDATE gene_sets SET conversation_id = %s WHERE id = %s",
            (str(CONVERSATION_ID), GENE_SET_ID),
        )
        connection.execute(
            "UPDATE control_sets SET conversation_id = %s WHERE id = %s",
            (str(CONVERSATION_ID), str(CONTROL_SET_ID)),
        )
        assert [str(held) for (held,) in _saved_in(seeded_database)] == [
            str(CONVERSATION_ID),
            str(CONVERSATION_ID),
        ]

        connection.execute(
            "DELETE FROM conversations WHERE id = %s", (str(CONVERSATION_ID),)
        )

    assert _saved_in(seeded_database) == [(None,), (None,)]


def test_the_downgrade_removes_the_column_and_keeps_the_sets(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert not any("conversation_id" in columns(seeded_database, t) for t in TABLES)
    assert rows(
        seeded_database, "SELECT id FROM gene_sets WHERE id = %s", (GENE_SET_ID,)
    ) == [(GENE_SET_ID,)]


def test_the_upgrade_runs_again_after_a_downgrade(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _saved_in(seeded_database) == [(None,), (None,)]
    assert rows(
        seeded_database,
        "SELECT conrelid::regclass::text, conname, confdeltype::text "
        "FROM pg_constraint WHERE conname = ANY(%s) ORDER BY conname",
        ([f"fk_{table}_conversation_id" for table in TABLES],),
    ) == [
        ("control_sets", "fk_control_sets_conversation_id", "n"),
        ("gene_sets", "fk_gene_sets_conversation_id", "n"),
    ]
