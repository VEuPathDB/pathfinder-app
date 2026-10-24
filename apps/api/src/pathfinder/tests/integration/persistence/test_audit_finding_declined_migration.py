from __future__ import annotations

import json
import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.tests._support.audit import NF54
from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_10_24_0002"
REVISION = "2026_10_24_0003"
_TARGET = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
_DECLINE = "UPDATE audit_findings SET status = 'declined'"


@pytest.fixture
def migrated(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_audit_finding_declined"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    user_id, run_id = str(uuid4()), str(uuid4())
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        connection.execute(
            "INSERT INTO audit_runs (id, user_id, site_id, scope, seed, stages) "
            "VALUES (%s, %s, 'plasmodb', '{}'::jsonb, 7, '{}'::jsonb)",
            (run_id, user_id),
        )
        connection.execute(
            "INSERT INTO audit_findings "
            "(run_id, check_name, genome, target, target_key, sampled, status) "
            "VALUES (%s, 'gene_length', %s, %s, %s, true, 'screened')",
            (
                run_id,
                NF54,
                json.dumps(_TARGET.model_dump(by_alias=True, mode="json")),
                _TARGET.key,
            ),
        )
    yield url
    drop_database(base_url, name)


def _declined(url: str) -> str | None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        try:
            connection.execute(_DECLINE)
        except psycopg.errors.IntegrityError as exc:
            return exc.diag.constraint_name
    return None


def test_the_older_constraint_refuses_a_declined_finding(migrated: str) -> None:
    assert _declined(migrated) == "ck_audit_findings_status"


def test_the_upgrade_admits_a_declined_finding(migrated: str) -> None:
    command.upgrade(alembic_config(migrated), REVISION)

    assert _declined(migrated) is None
    assert rows(migrated, "SELECT status FROM audit_findings") == [("declined",)]


def test_the_downgrade_stores_a_declined_finding_failed(migrated: str) -> None:
    command.upgrade(alembic_config(migrated), REVISION)
    _declined(migrated)

    command.downgrade(alembic_config(migrated), PREVIOUS_REVISION)

    assert rows(migrated, "SELECT status FROM audit_findings") == [("failed",)]
