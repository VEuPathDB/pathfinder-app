"""The verdict table and the review columns of a run, applied to a real database."""

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
from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    indexes,
    psycopg_url,
    rows,
    tables,
)

PREVIOUS_REVISION = "2026_10_22_0001"
REVISION = "2026_10_23_0001"
_TARGET = SingleGeneTarget(check="gene_length", genes=("EXA_0001",))
_VERDICT = json.dumps({"verdict": "no_error"})
_REVIEW = json.dumps({"alreadyKnown": "not_searched"})
_COLUMNS = (
    "id user_id application_id conversation_id run_id finding_id site_id origin "
    "verdict review model_id created_at"
)
_CHECKS = {
    "ck_audit_verdicts_origin",
    "ck_audit_verdicts_review",
    "ck_audit_verdicts_run",
}


@pytest.fixture
def migrated(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_audit_verdicts"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    command.upgrade(alembic_config(url), REVISION)
    yield url
    drop_database(base_url, name)


def _seed(url: str) -> tuple[str, str, int]:
    user_id, run_id = str(uuid4()), str(uuid4())
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        connection.execute(
            "INSERT INTO audit_runs (id, user_id, site_id, scope, seed, stages) "
            "VALUES (%s, %s, 'toxodb', '{}'::jsonb, 7, '{}'::jsonb)",
            (run_id, user_id),
        )
        finding = connection.execute(
            "INSERT INTO audit_findings "
            "(run_id, check_name, genome, target, target_key, sampled, status) "
            "VALUES (%s, 'gene_length', 'Examplea alpha A', %s, %s, true, 'screened') "
            "RETURNING id",
            (
                run_id,
                json.dumps(_TARGET.model_dump(by_alias=True, mode="json")),
                _TARGET.key,
            ),
        ).fetchone()
    assert finding is not None
    return user_id, run_id, finding[0]


def _refusal(
    url: str, user_id: str, run_id: str | None, finding_id: int | None, origin: str
) -> str | None:
    review = _REVIEW if origin == "review" else None
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        try:
            connection.execute(
                "INSERT INTO audit_verdicts (user_id, run_id, finding_id, site_id, "
                "origin, verdict, review, model_id) "
                "VALUES (%s, %s, %s, 'toxodb', %s, %s, %s, 'test:model')",
                (user_id, run_id, finding_id, origin, _VERDICT, review),
            )
        except psycopg.errors.IntegrityError as exc:
            return exc.diag.constraint_name
    return None


def test_the_verdict_table_stands_with_its_checks_and_indexes(migrated: str) -> None:
    assert "audit_verdicts" in tables(migrated)
    assert columns(migrated, "audit_verdicts") == set(_COLUMNS.split())
    assert {"review", "synthesis"} <= columns(migrated, "audit_runs")
    named = rows(
        migrated,
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'audit_verdicts'::regclass AND contype = 'c'",
    )
    assert {row[0] for row in named} == _CHECKS
    assert indexes(migrated, "audit_verdicts") == {
        "audit_verdicts_pkey",
        "uq_audit_verdicts_finding_id",
        "ix_audit_verdicts_run_id",
        "ix_audit_verdicts_user_app_conversation",
    }
    typed = rows(
        migrated,
        "SELECT table_name, column_name, data_type, character_maximum_length "
        "FROM information_schema.columns WHERE "
        "(table_name = 'audit_verdicts' AND column_name IN ('user_id', 'run_id')) "
        "OR (table_name = 'audit_runs' AND column_name IN ('review', 'synthesis')) "
        "ORDER BY table_name, column_name",
    )
    assert typed == [
        ("audit_runs", "review", "jsonb", None),
        ("audit_runs", "synthesis", "jsonb", None),
        ("audit_verdicts", "run_id", "character", 36),
        ("audit_verdicts", "user_id", "character", 36),
    ]


def test_a_review_names_its_finding_and_a_finding_names_its_run(
    migrated: str,
) -> None:
    user_id, run_id, finding_id = _seed(migrated)
    assert _refusal(migrated, user_id, run_id, None, "review") == (
        "ck_audit_verdicts_review"
    )
    assert _refusal(migrated, user_id, run_id, finding_id, "auditor") == (
        "ck_audit_verdicts_review"
    )
    assert _refusal(migrated, user_id, None, finding_id, "review") == (
        "ck_audit_verdicts_run"
    )
    assert _refusal(migrated, user_id, None, None, "guess") == (
        "ck_audit_verdicts_origin"
    )
    assert _refusal(migrated, user_id, None, None, "auditor") is None
    assert _refusal(migrated, user_id, run_id, finding_id, "review") is None
    assert _refusal(migrated, user_id, run_id, finding_id, "review") == (
        "uq_audit_verdicts_finding_id"
    )


def test_a_deleted_run_takes_its_verdicts_and_a_chat_verdict_stays(
    migrated: str,
) -> None:
    user_id, run_id, finding_id = _seed(migrated)
    assert _refusal(migrated, user_id, run_id, finding_id, "review") is None
    assert _refusal(migrated, user_id, None, None, "lead") is None
    with psycopg.connect(psycopg_url(migrated), autocommit=True) as connection:
        connection.execute("DELETE FROM audit_runs WHERE id = %s", (run_id,))
    assert rows(migrated, "SELECT origin FROM audit_verdicts") == [("lead",)]


def test_the_downgrade_drops_the_table_and_the_columns(migrated: str) -> None:
    command.downgrade(alembic_config(migrated), PREVIOUS_REVISION)
    assert "audit_verdicts" not in tables(migrated)
    assert not {"review", "synthesis"} & columns(migrated, "audit_runs")
