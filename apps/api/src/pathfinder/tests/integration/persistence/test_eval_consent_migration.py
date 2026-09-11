"""The consent column and the staging table, applied to a real database.

Consent defaults on, so an account that predates the notice is opted in and
the notice is what tells them. The staging table's constraint is the linkage
rule: promotion cannot keep the user.
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

PREVIOUS_REVISION = "2026_08_22_0001"
REVISION = "2026_08_23_0001"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()


def _stage_one(url: str, staging_id: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, user_id, source_conversation_id, site_id, assistant_id, "
            "content_hash, extract, status) "
            "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, '{}'::jsonb, 'staged')",
            (staging_id, str(USER_ID), str(CONVERSATION_ID), "a" * 64),
        )


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name) "
            "VALUES (%s, %s, 'plasmodb', 'kinases')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a user with no consent column."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_eval_consent"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_the_column_and_the_table_are_absent_before_the_upgrade(
    seeded_database: str,
) -> None:
    assert "eval_data_consent" not in columns(seeded_database, "users")
    assert columns(seeded_database, "eval_staged_cases") == set()


def test_the_upgrade_opts_every_existing_account_in(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    consent = rows(
        seeded_database,
        "SELECT eval_data_consent, eval_notice_seen_at FROM users WHERE id = %s",
        (str(USER_ID),),
    )
    assert consent == [(True, None)]


def test_the_upgrade_creates_the_staging_table(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    staged = columns(seeded_database, "eval_staged_cases")
    assert "user_id" in staged
    assert "content_hash" in staged
    assert "extract" in staged


def test_the_constraint_refuses_a_promoted_row_that_names_a_user(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    with (
        psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            "INSERT INTO eval_staged_cases "
            "(id, user_id, source_conversation_id, site_id, assistant_id, "
            "content_hash, extract, status) "
            "VALUES (%s, %s, %s, 'plasmodb', 'pathfinder', %s, NULL, 'promoted')",
            (str(uuid4()), str(USER_ID), str(CONVERSATION_ID), "b" * 64),
        )


def test_deleting_the_user_removes_their_staged_rows(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    staging_id = str(uuid4())
    _stage_one(seeded_database, staging_id)

    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute("DELETE FROM users WHERE id = %s", (str(USER_ID),))

    assert (
        rows(
            seeded_database,
            "SELECT id FROM eval_staged_cases WHERE id = %s",
            (staging_id,),
        )
        == []
    )


def test_the_downgrade_removes_both_and_keeps_the_user(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    _stage_one(seeded_database, str(uuid4()))

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "eval_data_consent" not in columns(seeded_database, "users")
    assert "eval_notice_seen_at" not in columns(seeded_database, "users")
    assert columns(seeded_database, "eval_staged_cases") == set()
    assert rows(
        seeded_database,
        "SELECT id FROM users WHERE id = %s",
        (str(USER_ID),),
    ) == [(str(USER_ID),)]
