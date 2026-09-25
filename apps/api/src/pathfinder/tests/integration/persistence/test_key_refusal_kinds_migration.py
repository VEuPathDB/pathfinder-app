"""A stored key may be marked refused for its credit or its permissions.

The downgrade keeps such a key refused, under the one refusal the older
constraint names for a provider's answer.
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
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_09_24_0003"
REVISION = "2026_09_24_0004"
USER_ID = uuid4()


def _mark(url: str, provider: str, refusal: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO user_provider_keys "
            "(id, user_id, application_id, provider, ciphertext, hint, "
            "refused_at, refusal) "
            "VALUES (%s, %s, 'pathfinder', %s, %s, 'WXYZ', now(), %s)",
            (str(uuid4()), str(USER_ID), provider, b"sealed", refusal),
        )


def _refusals(url: str) -> list[tuple[str, str]]:
    return [
        (provider, refusal)
        for provider, refusal in rows(
            url, "SELECT provider, refusal FROM user_provider_keys ORDER BY provider"
        )
    ]


@pytest.fixture
def old_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a user."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_key_refusal_kinds"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
    yield url
    drop_database(base_url, name)


def test_the_older_constraint_refuses_a_credit_refusal(old_database: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _mark(old_database, "anthropic", "no_credit")


def test_the_upgrade_admits_a_credit_and_a_permission_refusal(
    old_database: str,
) -> None:
    command.upgrade(alembic_config(old_database), REVISION)

    _mark(old_database, "anthropic", "no_credit")
    _mark(old_database, "google", "forbidden")
    _mark(old_database, "openai", "invalid")

    assert _refusals(old_database) == [
        ("anthropic", "no_credit"),
        ("google", "forbidden"),
        ("openai", "invalid"),
    ]
    with pytest.raises(psycopg.errors.CheckViolation):
        _mark(old_database, "openai", "declined")


def test_the_downgrade_keeps_each_key_refused(old_database: str) -> None:
    command.upgrade(alembic_config(old_database), REVISION)
    _mark(old_database, "anthropic", "no_credit")
    _mark(old_database, "google", "forbidden")

    command.downgrade(alembic_config(old_database), PREVIOUS_REVISION)

    assert _refusals(old_database) == [
        ("anthropic", "invalid"),
        ("google", "invalid"),
    ]
    with pytest.raises(psycopg.errors.CheckViolation):
        _mark(old_database, "openai", "no_credit")
