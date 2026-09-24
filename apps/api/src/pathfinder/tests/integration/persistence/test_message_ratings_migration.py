"""The rating table and the rated staging column, applied to a real database."""

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

PREVIOUS_REVISION = "2026_09_16_0003"
REVISION = "2026_09_24_0001"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
MESSAGE_ID = uuid4()
STAGED_ID = uuid4()


def _seed(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'kinases')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO messages (id, conversation_id, role) "
            "VALUES (%s, %s, 'assistant')",
            (str(MESSAGE_ID), str(CONVERSATION_ID)),
        )
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, user_id, source_conversation_id, site_id, assistant_id, "
            "content_hash, extract, status) "
            "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, '{}'::jsonb, 'staged')",
            (str(STAGED_ID), str(USER_ID), str(CONVERSATION_ID), "a" * 64),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding one staged extraction row."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_message_ratings"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed(url)
    yield url
    drop_database(base_url, name)


def test_the_upgrade_creates_the_table_and_the_indexes(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert columns(seeded_database, "message_ratings") == {
        "id",
        "message_id",
        "conversation_id",
        "user_id",
        "rating",
        "case_keys",
        "withheld_cases",
        "rated_at",
        "updated_at",
    }
    assert "rated_message_id" in columns(seeded_database, "eval_staged_cases")
    staged_indexes = indexes(seeded_database, "eval_staged_cases")
    assert "ix_eval_staged_cases_source_conversation" in staged_indexes
    assert "ix_eval_staged_cases_rated_message" in staged_indexes


def test_an_existing_staged_row_survives_the_upgrade(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert rows(
        seeded_database,
        "SELECT id, rated_message_id FROM eval_staged_cases",
    ) == [(str(STAGED_ID), None)]


def test_two_rated_rows_of_one_thread_both_stage(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        for content_hash in ("b" * 64, "c" * 64):
            connection.execute(
                "INSERT INTO eval_staged_cases "
                "(id, user_id, source_conversation_id, site_id, assistant_id, "
                "content_hash, extract, status, rated_message_id) "
                "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, "
                "'{}'::jsonb, 'staged', %s)",
                (
                    str(uuid4()),
                    str(USER_ID),
                    str(CONVERSATION_ID),
                    content_hash,
                    str(uuid4()),
                ),
            )

    assert rows(
        seeded_database,
        "SELECT count(*) FROM eval_staged_cases WHERE source_conversation_id = %s",
        (str(CONVERSATION_ID),),
    ) == [(3,)]


def test_a_promoted_row_that_keeps_its_message_is_refused(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    with (
        psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, site_id, assistant_id, content_hash, status, rated_message_id) "
            "VALUES (%s, 'plasmodb', 'pathfinder', %s, 'promoted', %s)",
            (str(uuid4()), "d" * 64, str(MESSAGE_ID)),
        )


def test_deleting_the_message_deletes_its_rating(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO message_ratings (message_id, conversation_id, user_id, rating) "
            "VALUES (%s, %s, %s, 'like')",
            (str(MESSAGE_ID), str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute("DELETE FROM messages WHERE id = %s", (str(MESSAGE_ID),))

    assert rows(seeded_database, "SELECT count(*) FROM message_ratings") == [(0,)]


def test_the_downgrade_restores_the_single_thread_index(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert columns(seeded_database, "message_ratings") == set()
    assert "rated_message_id" not in columns(seeded_database, "eval_staged_cases")
    assert "ix_eval_staged_cases_source_conversation" in indexes(
        seeded_database, "eval_staged_cases"
    )
    assert rows(seeded_database, "SELECT id FROM eval_staged_cases") == [
        (str(STAGED_ID),)
    ]
    with (
        psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection,
        pytest.raises(psycopg.errors.UniqueViolation),
    ):
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, user_id, source_conversation_id, site_id, assistant_id, "
            "content_hash, extract, status) "
            "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, '{}'::jsonb, 'staged')",
            (str(uuid4()), str(USER_ID), str(CONVERSATION_ID), "e" * 64),
        )
