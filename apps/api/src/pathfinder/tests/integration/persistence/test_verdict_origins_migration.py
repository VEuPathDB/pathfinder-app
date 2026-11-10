from __future__ import annotations

import json
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

PREVIOUS_REVISION = "2026_11_09_0003"
REVISION = "2026_11_10_0001"
_VERDICT = json.dumps({"verdict": "no_error"})


@pytest.fixture
def previous(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_verdict_origins"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def _insert(url: str, user_id: str, origin: str) -> str | None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        try:
            connection.execute(
                "INSERT INTO audit_verdicts (user_id, site_id, origin, verdict, model_id) "
                "VALUES (%s, 'toxodb', %s, %s, 'test:model')",
                (user_id, origin, _VERDICT),
            )
        except psycopg.errors.IntegrityError as exc:
            return exc.diag.constraint_name
    return None


def _user(url: str) -> str:
    user_id = str(uuid4())
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
    return user_id


def test_the_upgrade_deletes_the_verdicts_of_the_removed_origins(previous: str) -> None:
    user_id = _user(previous)
    for origin in ("auditor", "lead", "verification"):
        assert _insert(previous, user_id, origin) is None
    command.upgrade(alembic_config(previous), REVISION)
    assert rows(previous, "SELECT origin FROM audit_verdicts") == [("auditor",)]


def test_a_removed_origin_is_refused_after_the_upgrade(previous: str) -> None:
    command.upgrade(alembic_config(previous), REVISION)
    user_id = _user(previous)
    assert _insert(previous, user_id, "lead") == "ck_audit_verdicts_origin"
    assert _insert(previous, user_id, "verification") == "ck_audit_verdicts_origin"
    assert _insert(previous, user_id, "auditor") is None


def test_the_downgrade_admits_the_removed_origins_again(previous: str) -> None:
    command.upgrade(alembic_config(previous), REVISION)
    command.downgrade(alembic_config(previous), PREVIOUS_REVISION)
    _insert(previous, _user(previous), "lead")
    assert rows(previous, "SELECT origin FROM audit_verdicts") == [("lead",)]
