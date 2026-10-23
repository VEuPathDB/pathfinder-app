"""The audit tables, applied to a real database: their columns, keys and cascades."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from typing import Any, get_args
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from psycopg.abc import QueryNoTemplate
from psycopg.sql import SQL, Identifier
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import defer
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from pathfinder.domain.audit.findings import (
    Certainty,
    EvidenceStatus,
    FindingStatus,
    RelativesEvidence,
)
from pathfinder.domain.audit.scope import (
    AuditScope,
    GenomeRole,
    GenomeStatus,
    SingleGeneTarget,
)
from pathfinder.domain.audit.stages import RunStages, RunStatus
from pathfinder.persistence.models import (
    AuditEvidence,
    AuditEvidenceRecord,
    AuditFinding,
    AuditFindingRecord,
    AuditGenome,
    AuditGenomeState,
    AuditRun,
    AuditRunRecord,
    User,
)
from pathfinder.tests._support.audit import NF54
from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    psycopg_url,
    rows,
    tables,
)

PREVIOUS_REVISION = "2026_10_15_0001"
REVISION = "2026_10_21_0001"
_AUDIT_TABLES = ("audit_evidence", "audit_findings", "audit_genomes", "audit_runs")
_TARGET = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
_SCOPE = AuditScope(site_id="plasmodb", targets=(_TARGET,))
_RELATIVES = RelativesEvidence(
    reference_gene="PF3D7_0000100",
    reference_length=420,
    model_length=210,
    relatives_median=418.0,
)


@pytest.fixture
def migrated(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_audit_tables"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    command.upgrade(alembic_config(url), REVISION)
    yield url
    drop_database(base_url, name)


@pytest.fixture
def at_head(migrated: str) -> str:
    command.upgrade(alembic_config(migrated), "head")
    return migrated


def _seed(url: str) -> tuple[str, str, int]:
    user_id, conversation_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        connection.execute(
            "INSERT INTO conversations (id, user_id, site_id, name, assistant_id) "
            "VALUES (%s, %s, 'plasmodb', '', 'pathfinder')",
            (conversation_id, user_id),
        )
        connection.execute(
            "INSERT INTO audit_runs "
            "(id, user_id, conversation_id, site_id, scope, seed, stages) "
            "VALUES (%s, %s, %s, 'plasmodb', '{}'::jsonb, 7, '{}'::jsonb)",
            (run_id, user_id, conversation_id),
        )
        connection.execute(
            "INSERT INTO audit_genomes (run_id, organism, role, status) "
            "VALUES (%s, %s, 'audited', 'pending')",
            (run_id, NF54),
        )
        finding = connection.execute(
            "INSERT INTO audit_findings "
            "(run_id, check_name, genome, target, target_key, sampled, status) "
            "VALUES (%s, 'gene_length', %s, %s, %s, true, 'screened') "
            "RETURNING id",
            (run_id, NF54, json.dumps(_json(_TARGET)), _TARGET.key),
        ).fetchone()
        assert finding is not None
        connection.execute(
            "INSERT INTO audit_evidence (finding_id, kind, status) "
            "VALUES (%s, 'relatives', 'pending')",
            (finding[0],),
        )
    return user_id, conversation_id, finding[0]


def _json(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(by_alias=True, mode="json")


def _counts(url: str) -> list[int]:
    return [
        rows(url, SQL("SELECT count(*) FROM {}").format(Identifier(table)))[0][0]
        for table in _AUDIT_TABLES
    ]


_UNIT = "requests attempts stopped message"
_COLUMNS = {
    "audit_runs": (
        "id user_id application_id conversation_id site_id release scope seed status "
        "stages sealed_token deadline_at created_at updated_at finished_at"
    ),
    "audit_genomes": (
        "id run_id organism role status gene_count genes priority reference_strain "
        f"{_UNIT} updated_at"
    ),
    "audit_findings": (
        "id run_id check_name genome screened_genome paired_genome target target_key "
        f"sampled status error_type certainty judged impact weighing {_UNIT} "
        "created_at updated_at"
    ),
    "audit_evidence": (
        f"id finding_id kind status payload {_UNIT} created_at updated_at"
    ),
}


def test_the_four_tables_stand_with_their_columns(migrated: str) -> None:
    assert set(_AUDIT_TABLES) <= tables(migrated)
    assert {table: columns(migrated, table) for table in _COLUMNS} == {
        table: set(names.split()) for table, names in _COLUMNS.items()
    }


def test_a_deleted_thread_keeps_its_run_and_a_deleted_user_takes_everything(
    migrated: str,
) -> None:
    user_id, conversation_id, _ = _seed(migrated)
    assert _counts(migrated) == [1, 1, 1, 1]
    with psycopg.connect(psycopg_url(migrated), autocommit=True) as connection:
        connection.execute(
            "DELETE FROM conversations WHERE id = %s", (conversation_id,)
        )
    assert rows(migrated, "SELECT conversation_id, status FROM audit_runs") == [
        (None, "planned")
    ]
    with psycopg.connect(psycopg_url(migrated), autocommit=True) as connection:
        connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
    assert _counts(migrated) == [0, 0, 0, 0]


_REFUSED = [
    (
        "UPDATE audit_runs SET status = 'finished'",
        "ck_audit_runs_finished_at",
    ),
    (
        "UPDATE audit_runs SET finished_at = now()",
        "ck_audit_runs_finished_at",
    ),
    (
        "UPDATE audit_findings SET status = 'confirmed', error_type = 'split_model'",
        "ck_audit_findings_error_has_certainty",
    ),
    (
        "UPDATE audit_findings SET error_type = 'split_model', certainty = 'medium'",
        "ck_audit_findings_error_when_confirmed",
    ),
    (
        "UPDATE audit_findings SET sampled = false",
        "ck_audit_findings_sampled_status",
    ),
    (
        "UPDATE audit_findings SET status = 'unsampled'",
        "ck_audit_findings_sampled_status",
    ),
    (
        "UPDATE audit_evidence SET status = 'stored'",
        "ck_audit_evidence_stored_has_payload",
    ),
    (
        "UPDATE audit_evidence SET payload = '{}'::jsonb",
        "ck_audit_evidence_stored_has_payload",
    ),
    (
        (
            "INSERT INTO audit_genomes (run_id, organism, role, status) "
            "SELECT run_id, organism, 'comparison', 'pending' FROM audit_genomes"
        ),
        "uq_audit_genomes_run_organism",
    ),
    (
        (
            "INSERT INTO audit_findings "
            "(run_id, check_name, target, target_key, sampled, status) "
            "SELECT run_id, check_name, target, target_key, true, 'screened' "
            "FROM audit_findings"
        ),
        "uq_audit_findings_run_target",
    ),
    (
        (
            "INSERT INTO audit_evidence (finding_id, kind, status) "
            "SELECT finding_id, kind, 'pending' FROM audit_evidence"
        ),
        "uq_audit_evidence_finding_kind",
    ),
]
_ACCEPTED = [
    "UPDATE audit_runs SET status = 'finished', finished_at = now()",
    "UPDATE audit_runs SET release = repeat('9', 64)",
    (
        "UPDATE audit_findings SET status = 'confirmed', "
        "error_type = 'split_model', certainty = 'medium'"
    ),
    "UPDATE audit_findings SET status = 'unsampled', sampled = false",
    "UPDATE audit_evidence SET status = 'stored', payload = '{}'::jsonb",
]
_DOMAIN_VALUES = [
    ("ck_audit_runs_status", RunStatus),
    ("ck_audit_genomes_role", GenomeRole),
    ("ck_audit_genomes_status", GenomeStatus),
    ("ck_audit_findings_status", FindingStatus),
    ("ck_audit_findings_certainty", Certainty),
    ("ck_audit_evidence_status", EvidenceStatus),
]


def _refusal(url: str, statement: QueryNoTemplate) -> str | None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        try:
            connection.execute(statement)
        except psycopg.errors.IntegrityError as exc:
            return exc.diag.constraint_name
    return None


@pytest.mark.parametrize(("statement", "constraint"), _REFUSED)
def test_a_row_that_breaks_a_rule_is_refused_by_that_rule(
    migrated: str, statement: QueryNoTemplate, constraint: str
) -> None:
    _seed(migrated)
    assert _refusal(migrated, statement) == constraint


@pytest.mark.parametrize("statement", _ACCEPTED)
def test_a_row_that_keeps_every_rule_is_stored(
    migrated: str, statement: QueryNoTemplate
) -> None:
    _seed(migrated)
    assert _refusal(migrated, statement) is None
    assert _counts(migrated) == [1, 1, 1, 1]


@pytest.mark.parametrize(("constraint", "literal"), _DOMAIN_VALUES)
def test_a_checked_column_takes_exactly_the_domain_values(
    migrated: str, constraint: str, literal: object
) -> None:
    definition = rows(
        migrated,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    )
    assert len(definition) == 1
    assert set(re.findall(r"'([^']*)'::", definition[0][0])) == set(get_args(literal))


async def _write_a_run(session: AsyncSession) -> UUID:
    user = User(id=uuid4())
    session.add(user)
    await session.flush()
    run = AuditRun(
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        scope=_json(_SCOPE),
        seed=7,
        stages=_json(RunStages()),
    )
    session.add(run)
    await session.flush()
    finding = AuditFinding(
        run_id=run.id,
        check_name=_TARGET.check,
        genome=NF54,
        target=_json(_TARGET),
        target_key=_TARGET.key,
        sampled=True,
        status="confirmed",
        error_type="truncated_model",
        certainty="high",
    )
    genome = AuditGenome(
        run_id=run.id, organism=NF54, role="audited", status="collected"
    )
    session.add_all([finding, genome])
    await session.flush()
    session.add_all(
        [
            AuditEvidence(
                finding_id=finding.id,
                kind="confirmation",
                status="failed",
                payload=None,
                message="the record holds no protein",
            ),
            AuditEvidence(
                finding_id=finding.id,
                kind="relatives",
                status="stored",
                payload=_json(_RELATIVES),
            ),
        ]
    )
    run_id = run.id
    await session.commit()
    return run_id


async def test_the_models_store_an_absent_payload_as_null_and_read_every_row_back(
    at_head: str,
) -> None:
    engine = create_async_engine(at_head, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            run_id = await _write_a_run(session)
        async with AsyncSession(engine) as session:
            run = (await session.scalars(select(AuditRun))).one()
            genome = (
                await session.scalars(
                    select(AuditGenome).options(defer(AuditGenome.genes))
                )
            ).one()
            finding = (await session.scalars(select(AuditFinding))).one()
            evidence = (
                await session.scalars(
                    select(AuditEvidence).order_by(AuditEvidence.kind)
                )
            ).all()
            run_record = AuditRunRecord.model_validate(run)
            genome_state = AuditGenomeState.model_validate(genome)
            finding_record = AuditFindingRecord.model_validate(finding)
            evidence_records = [AuditEvidenceRecord.model_validate(e) for e in evidence]
    finally:
        await engine.dispose()

    assert rows(
        at_head, "SELECT kind, payload IS NULL FROM audit_evidence ORDER BY kind"
    ) == [("confirmation", True), ("relatives", False)]
    assert (run_record.id, run_record.status, run_record.seed) == (run_id, "planned", 7)
    assert run_record.scope == _SCOPE
    assert run_record.stages == RunStages()
    assert genome_state == AuditGenomeState(
        organism=NF54,
        role="audited",
        status="collected",
        gene_count=0,
        requests=0,
        attempts=0,
        stopped=0,
        message=None,
        priority=None,
        reference_strain=None,
    )
    assert finding_record == AuditFindingRecord(
        id=finding.id,
        run_id=run_id,
        genome=NF54,
        target=_TARGET,
        sampled=True,
        status="confirmed",
        error_type="truncated_model",
        certainty="high",
        screened_genome="",
        paired_genome=None,
        judged=True,
        impact=None,
        weighing=None,
        requests=0,
        attempts=0,
        stopped=0,
        message=None,
    )
    assert [(r.kind, r.status, r.payload, r.message) for r in evidence_records] == [
        ("confirmation", "failed", None, "the record holds no protein"),
        ("relatives", "stored", _RELATIVES, None),
    ]


def test_the_downgrade_drops_the_four_tables(migrated: str) -> None:
    command.downgrade(alembic_config(migrated), PREVIOUS_REVISION)
    assert set(_AUDIT_TABLES) & tables(migrated) == set()
    assert "users" in tables(migrated)
