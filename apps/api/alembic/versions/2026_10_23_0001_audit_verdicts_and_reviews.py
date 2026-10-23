"""Add the verdict table and the review state and synthesis of an audit run.

Revision ID: 2026_10_23_0001
Revises: 2026_10_22_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_10_23_0001"
down_revision: str | Sequence[str] | None = "2026_10_22_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_runs", sqlalchemy.Column("review", postgresql.JSONB()))
    op.add_column("audit_runs", sqlalchemy.Column("synthesis", postgresql.JSONB()))
    op.create_table(
        "audit_verdicts",
        sqlalchemy.Column(
            "id", sqlalchemy.BigInteger(), sqlalchemy.Identity(), nullable=False
        ),
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
        sqlalchemy.Column("run_id", sqlalchemy.CHAR(length=36), nullable=True),
        sqlalchemy.Column("finding_id", sqlalchemy.BigInteger(), nullable=True),
        sqlalchemy.Column("site_id", sqlalchemy.String(length=100), nullable=False),
        sqlalchemy.Column("origin", sqlalchemy.String(length=16), nullable=False),
        sqlalchemy.Column("verdict", postgresql.JSONB(), nullable=False),
        sqlalchemy.Column("review", postgresql.JSONB(), nullable=True),
        sqlalchemy.Column("model_id", sqlalchemy.Text(), nullable=False),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            nullable=False,
            server_default=sqlalchemy.text("now()"),
        ),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sqlalchemy.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_audit_verdicts_conversation_id",
            ondelete="SET NULL",
        ),
        sqlalchemy.ForeignKeyConstraint(
            ["run_id"], ["audit_runs.id"], ondelete="CASCADE"
        ),
        sqlalchemy.ForeignKeyConstraint(
            ["finding_id"], ["audit_findings.id"], ondelete="CASCADE"
        ),
        sqlalchemy.UniqueConstraint("finding_id", name="uq_audit_verdicts_finding_id"),
        sqlalchemy.CheckConstraint(
            "origin IN ('auditor', 'lead', 'verification', 'review')",
            name="ck_audit_verdicts_origin",
        ),
        sqlalchemy.CheckConstraint(
            "(origin = 'review') = (finding_id IS NOT NULL) "
            "AND (origin = 'review') = (review IS NOT NULL)",
            name="ck_audit_verdicts_review",
        ),
        sqlalchemy.CheckConstraint(
            "finding_id IS NULL OR run_id IS NOT NULL",
            name="ck_audit_verdicts_run",
        ),
    )
    op.create_index("ix_audit_verdicts_run_id", "audit_verdicts", ["run_id"])
    op.create_index(
        "ix_audit_verdicts_user_app_conversation",
        "audit_verdicts",
        ["user_id", "application_id", "conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_verdicts_user_app_conversation", table_name="audit_verdicts"
    )
    op.drop_index("ix_audit_verdicts_run_id", table_name="audit_verdicts")
    op.drop_table("audit_verdicts")
    op.drop_column("audit_runs", "synthesis")
    op.drop_column("audit_runs", "review")
