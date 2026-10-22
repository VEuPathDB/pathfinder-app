"""Add the audit tables: a run, its collected genomes, its findings and their evidence.

Revision ID: 2026_10_21_0001
Revises: 2026_10_15_0001
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_10_21_0001"
down_revision: str | Sequence[str] | None = "2026_10_15_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sqlalchemy.text("now()")
_ZERO = sqlalchemy.text("0")


def _counter(name: str) -> sqlalchemy.Column[int]:
    return sqlalchemy.Column(
        name, sqlalchemy.Integer(), nullable=False, server_default=_ZERO
    )


def _stamp(name: str) -> sqlalchemy.Column[datetime]:
    return sqlalchemy.Column(
        name, sqlalchemy.DateTime(timezone=True), nullable=False, server_default=_NOW
    )


def _identity() -> sqlalchemy.Column[int]:
    return sqlalchemy.Column(
        "id", sqlalchemy.BigInteger(), sqlalchemy.Identity(), nullable=False
    )


def _unit_columns() -> list[sqlalchemy.Column[int] | sqlalchemy.Column[str]]:
    return [
        _counter("requests"),
        _counter("attempts"),
        _counter("stopped"),
        sqlalchemy.Column("message", sqlalchemy.Text(), nullable=True),
    ]


def _runs() -> None:
    op.create_table(
        "audit_runs",
        sqlalchemy.Column("id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column("user_id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column(
            "application_id",
            sqlalchemy.String(length=64),
            nullable=False,
            server_default="default",
        ),
        sqlalchemy.Column(
            "conversation_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sqlalchemy.Column("site_id", sqlalchemy.String(length=100), nullable=False),
        sqlalchemy.Column("release", sqlalchemy.Text(), nullable=True),
        sqlalchemy.Column("scope", postgresql.JSONB(), nullable=False),
        sqlalchemy.Column("seed", sqlalchemy.BigInteger(), nullable=False),
        sqlalchemy.Column(
            "status",
            sqlalchemy.String(length=16),
            nullable=False,
            server_default="planned",
        ),
        sqlalchemy.Column("stages", postgresql.JSONB(), nullable=False),
        sqlalchemy.Column("sealed_token", sqlalchemy.LargeBinary(), nullable=True),
        sqlalchemy.Column(
            "deadline_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        _stamp("created_at"),
        _stamp("updated_at"),
        sqlalchemy.Column(
            "finished_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sqlalchemy.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_audit_runs_conversation_id",
            ondelete="SET NULL",
        ),
        sqlalchemy.CheckConstraint(
            "status IN ('planned', 'running', 'finished')", name="ck_audit_runs_status"
        ),
        sqlalchemy.CheckConstraint(
            "(status = 'finished') = (finished_at IS NOT NULL)",
            name="ck_audit_runs_finished_at",
        ),
    )
    op.create_index(
        "ix_audit_runs_user_app", "audit_runs", ["user_id", "application_id"]
    )
    op.create_index("ix_audit_runs_conversation_id", "audit_runs", ["conversation_id"])


def _genomes() -> None:
    op.create_table(
        "audit_genomes",
        _identity(),
        sqlalchemy.Column("run_id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column("organism", sqlalchemy.String(length=255), nullable=False),
        sqlalchemy.Column("role", sqlalchemy.String(length=16), nullable=False),
        sqlalchemy.Column("status", sqlalchemy.String(length=16), nullable=False),
        _counter("gene_count"),
        sqlalchemy.Column(
            "genes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::jsonb"),
        ),
        sqlalchemy.Column("priority", postgresql.JSONB(), nullable=True),
        sqlalchemy.Column("reference_strain", sqlalchemy.Boolean(), nullable=True),
        *_unit_columns(),
        _stamp("updated_at"),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(
            ["run_id"], ["audit_runs.id"], ondelete="CASCADE"
        ),
        sqlalchemy.UniqueConstraint(
            "run_id", "organism", name="uq_audit_genomes_run_organism"
        ),
        sqlalchemy.CheckConstraint(
            "role IN ('audited', 'comparison')", name="ck_audit_genomes_role"
        ),
        sqlalchemy.CheckConstraint(
            "status IN "
            "('pending', 'trying', 'collected', 'failed', 'unreached', 'unread')",
            name="ck_audit_genomes_status",
        ),
    )


def _findings() -> None:
    op.create_table(
        "audit_findings",
        _identity(),
        sqlalchemy.Column("run_id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column("check_name", sqlalchemy.String(length=32), nullable=False),
        sqlalchemy.Column(
            "genome", sqlalchemy.String(length=255), nullable=False, server_default=""
        ),
        sqlalchemy.Column(
            "screened_genome",
            sqlalchemy.String(length=255),
            nullable=False,
            server_default="",
        ),
        sqlalchemy.Column(
            "paired_genome", sqlalchemy.String(length=255), nullable=True
        ),
        sqlalchemy.Column("target", postgresql.JSONB(), nullable=False),
        sqlalchemy.Column("target_key", sqlalchemy.String(length=512), nullable=False),
        sqlalchemy.Column("sampled", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column("status", sqlalchemy.String(length=16), nullable=False),
        sqlalchemy.Column("error_type", sqlalchemy.String(length=48), nullable=True),
        sqlalchemy.Column("certainty", sqlalchemy.String(length=8), nullable=True),
        sqlalchemy.Column(
            "judged",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("true"),
        ),
        sqlalchemy.Column("impact", sqlalchemy.Double(), nullable=True),
        sqlalchemy.Column("weighing", postgresql.JSONB(), nullable=True),
        *_unit_columns(),
        _stamp("created_at"),
        _stamp("updated_at"),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(
            ["run_id"], ["audit_runs.id"], ondelete="CASCADE"
        ),
        sqlalchemy.UniqueConstraint(
            "run_id", "target_key", name="uq_audit_findings_run_target"
        ),
        sqlalchemy.CheckConstraint(
            "status IN "
            "('screened', 'unsampled', 'trying', 'confirmed', 'failed', 'unreached', "
            "'unread')",
            name="ck_audit_findings_status",
        ),
        sqlalchemy.CheckConstraint(
            "(error_type IS NULL) = (certainty IS NULL)",
            name="ck_audit_findings_error_has_certainty",
        ),
        sqlalchemy.CheckConstraint(
            "certainty IS NULL OR certainty IN ('high', 'medium', 'low')",
            name="ck_audit_findings_certainty",
        ),
        sqlalchemy.CheckConstraint(
            "error_type IS NULL OR status = 'confirmed'",
            name="ck_audit_findings_error_when_confirmed",
        ),
        sqlalchemy.CheckConstraint(
            "sampled = (status <> 'unsampled')",
            name="ck_audit_findings_sampled_status",
        ),
        sqlalchemy.CheckConstraint(
            "impact IS NULL OR error_type IS NOT NULL",
            name="ck_audit_findings_impact_when_named",
        ),
        sqlalchemy.CheckConstraint(
            "(impact IS NULL) = (weighing IS NULL)",
            name="ck_audit_findings_impact_weighed",
        ),
        sqlalchemy.CheckConstraint(
            "judged OR (status = 'confirmed' AND error_type IS NULL)",
            name="ck_audit_findings_judged",
        ),
    )
    op.create_index(
        "ix_audit_findings_run_status", "audit_findings", ["run_id", "status"]
    )
    op.create_index(
        "ix_audit_findings_run_genome_check",
        "audit_findings",
        ["run_id", "genome", "check_name"],
    )
    op.create_index(
        "ix_audit_findings_run_impact",
        "audit_findings",
        ["run_id", sqlalchemy.text("impact DESC NULLS LAST"), "id"],
    )


def _evidence() -> None:
    op.create_table(
        "audit_evidence",
        _identity(),
        sqlalchemy.Column("finding_id", sqlalchemy.BigInteger(), nullable=False),
        sqlalchemy.Column("kind", sqlalchemy.String(length=32), nullable=False),
        sqlalchemy.Column("status", sqlalchemy.String(length=16), nullable=False),
        sqlalchemy.Column("payload", postgresql.JSONB(), nullable=True),
        *_unit_columns(),
        _stamp("created_at"),
        _stamp("updated_at"),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(
            ["finding_id"], ["audit_findings.id"], ondelete="CASCADE"
        ),
        sqlalchemy.UniqueConstraint(
            "finding_id", "kind", name="uq_audit_evidence_finding_kind"
        ),
        sqlalchemy.CheckConstraint(
            "status IN "
            "('pending', 'trying', 'stored', 'failed', 'unreached', 'unread')",
            name="ck_audit_evidence_status",
        ),
        sqlalchemy.CheckConstraint(
            "(status = 'stored') = (payload IS NOT NULL)",
            name="ck_audit_evidence_stored_has_payload",
        ),
    )


def upgrade() -> None:
    _runs()
    _genomes()
    _findings()
    _evidence()


def downgrade() -> None:
    op.drop_table("audit_evidence")
    op.drop_index("ix_audit_findings_run_impact", table_name="audit_findings")
    op.drop_index("ix_audit_findings_run_genome_check", table_name="audit_findings")
    op.drop_index("ix_audit_findings_run_status", table_name="audit_findings")
    op.drop_table("audit_findings")
    op.drop_table("audit_genomes")
    op.drop_index("ix_audit_runs_conversation_id", table_name="audit_runs")
    op.drop_index("ix_audit_runs_user_app", table_name="audit_runs")
    op.drop_table("audit_runs")
