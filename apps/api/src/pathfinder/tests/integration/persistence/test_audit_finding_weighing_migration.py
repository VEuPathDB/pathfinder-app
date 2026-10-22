"""A finding's impact, its weighing and its judged mark, applied to a real database."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg.abc import QueryNoTemplate
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

REVISION = "2026_10_21_0001"
_TARGET = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
_UNJUDGED = (
    "UPDATE audit_findings SET status = 'confirmed', judged = false, "
    "message = 'GAP: no DNA to read'"
)
_NAMED = (
    "UPDATE audit_findings SET status = 'confirmed', "
    "error_type = 'truncated_model', certainty = 'high'"
)


@pytest.fixture
def migrated(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_audit_finding_weighing"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), REVISION)
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


def _refusal(url: str, *statements: QueryNoTemplate) -> str | None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        try:
            for statement in statements:
                connection.execute(statement)
        except psycopg.errors.IntegrityError as exc:
            return exc.diag.constraint_name
    return None


def test_the_findings_of_a_run_are_indexed_in_the_order_they_are_paged(
    migrated: str,
) -> None:
    index = (
        "CREATE INDEX ix_audit_findings_run_impact ON public.audit_findings "
        "USING btree (run_id, impact DESC NULLS LAST, id)"
    )
    indexed = "SELECT indexdef FROM pg_indexes WHERE indexdef = %s"
    assert rows(migrated, indexed, (index,)) == [(index,)]
    assert rows(
        migrated,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'audit_findings' "
        "AND column_name IN ('impact', 'weighing', 'judged') ORDER BY column_name",
    ) == [("impact", "double precision"), ("judged", "boolean"), ("weighing", "jsonb")]


@pytest.mark.parametrize(
    ("statements", "constraint"),
    [
        (
            (_NAMED, "UPDATE audit_findings SET impact = 0.5"),
            "ck_audit_findings_impact_weighed",
        ),
        (
            ("UPDATE audit_findings SET impact = 0.5, weighing = '{}'::jsonb",),
            "ck_audit_findings_impact_when_named",
        ),
        (("UPDATE audit_findings SET judged = false",), "ck_audit_findings_judged"),
        (
            (_NAMED, "UPDATE audit_findings SET judged = false"),
            "ck_audit_findings_judged",
        ),
        (
            (_NAMED, "UPDATE audit_findings SET impact = 0.5, weighing = '{}'::jsonb"),
            None,
        ),
        ((_UNJUDGED,), None),
    ],
)
def test_an_impact_needs_its_weighing_and_a_named_error(
    migrated: str, statements: tuple[QueryNoTemplate, ...], constraint: str | None
) -> None:
    assert _refusal(migrated, *statements) == constraint
