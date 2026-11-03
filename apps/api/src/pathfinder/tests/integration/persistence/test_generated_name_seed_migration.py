"""The seed of a generated strategy name, applied to a real database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg.types.json import Jsonb
from testcontainers.community.postgres import PostgresContainer

from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_10_30_0001"
REVISION = "2026_11_03_0001"
USER_ID = uuid4()
CONVERSATION_ID = uuid4()
SEED = {"step_b": {"organism": "Pf3D7"}, "step_a": {}}


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        connection.execute(
            "INSERT INTO conversations "
            "(id, user_id, application_id, assistant_id, site_id, name) "
            "VALUES (%s, %s, 'pathfinder', 'pathfinder', 'plasmodb', 'Kinases')",
            (str(CONVERSATION_ID), str(USER_ID)),
        )
        connection.execute(
            "INSERT INTO conversation_strategies "
            "(conversation_id, strategy_ast, imported_saved_strategy_ids, "
            "generated_name_steps) VALUES (%s, '{}', '[]', '[\"step_a\"]')",
            (str(CONVERSATION_ID),),
        )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a generated name's steps."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_generated_name_seed"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_a_name_stored_with_only_its_steps_reads_as_a_person_chose_it(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    held = columns(seeded_database, "conversation_strategies")
    assert ("generated_name_steps" in held, "generated_name_seed" in held) == (
        False,
        True,
    )
    assert rows(
        seeded_database, "SELECT generated_name_seed FROM conversation_strategies"
    ) == [(None,)]


def test_the_downgrade_keeps_the_steps_of_the_seed(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)
    with psycopg.connect(psycopg_url(seeded_database), autocommit=True) as connection:
        connection.execute(
            "UPDATE conversation_strategies SET generated_name_seed = %s",
            (Jsonb(SEED),),
        )

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "generated_name_seed" not in columns(
        seeded_database, "conversation_strategies"
    )
    assert rows(
        seeded_database, "SELECT generated_name_steps FROM conversation_strategies"
    ) == [(["step_a", "step_b"],)]
