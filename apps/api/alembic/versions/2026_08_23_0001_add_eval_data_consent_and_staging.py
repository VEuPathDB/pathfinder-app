"""add_eval_data_consent_and_staging

Revision ID: 2026_08_23_0001
Revises: 2026_08_22_0001
Create Date: 2026-08-23 00:00:00.000000

Eval-data consent on the user, and the staging queue extraction writes into.
The consent column is additive and defaults on, which is the ruled default.
The staging table's check constraint is the linkage rule: a staged row names
its user and thread, a promoted row names neither and holds no extract.
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_08_23_0001"
down_revision: str | Sequence[str] | None = "2026_08_22_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINKAGE_ENDS_AT_PROMOTION = (
    "(status = 'staged'"
    " AND user_id IS NOT NULL"
    " AND source_conversation_id IS NOT NULL"
    " AND extract IS NOT NULL)"
    " OR "
    "(status = 'promoted'"
    " AND user_id IS NULL"
    " AND source_conversation_id IS NULL"
    " AND extract IS NULL)"
)


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column(
            "eval_data_consent",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("true"),
        ),
    )
    op.add_column(
        "users",
        sqlalchemy.Column(
            "eval_notice_seen_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
    )

    op.create_table(
        "eval_staged_cases",
        sqlalchemy.Column("id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column("user_id", sqlalchemy.CHAR(length=36), nullable=True),
        sqlalchemy.Column(
            "source_conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sqlalchemy.Column(
            "application_id",
            sqlalchemy.String(length=64),
            nullable=False,
            server_default="pathfinder",
        ),
        sqlalchemy.Column("site_id", sqlalchemy.String(length=50), nullable=False),
        sqlalchemy.Column("assistant_id", sqlalchemy.String(length=64), nullable=False),
        sqlalchemy.Column("content_hash", sqlalchemy.String(length=64), nullable=False),
        sqlalchemy.Column("extract", postgresql.JSONB(), nullable=True),
        sqlalchemy.Column(
            "status",
            sqlalchemy.String(length=16),
            nullable=False,
            server_default="staged",
        ),
        sqlalchemy.Column("corpus_name", sqlalchemy.String(length=128), nullable=True),
        sqlalchemy.Column(
            "staged_at",
            sqlalchemy.DateTime(timezone=True),
            nullable=False,
            server_default=sqlalchemy.text("now()"),
        ),
        sqlalchemy.Column(
            "promoted_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sqlalchemy.ForeignKeyConstraint(
            ["source_conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sqlalchemy.CheckConstraint(
            "status IN ('staged', 'promoted')",
            name="ck_eval_staged_cases_status",
        ),
        sqlalchemy.CheckConstraint(
            _LINKAGE_ENDS_AT_PROMOTION,
            name="ck_eval_staged_cases_linkage_ends_at_promotion",
        ),
        sqlalchemy.UniqueConstraint(
            "content_hash", name="uq_eval_staged_cases_content_hash"
        ),
    )
    op.create_index(
        "ix_eval_staged_cases_source_conversation",
        "eval_staged_cases",
        ["source_conversation_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("source_conversation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_eval_staged_cases_user_id",
        "eval_staged_cases",
        ["user_id"],
    )
    op.create_index(
        "ix_eval_staged_cases_status",
        "eval_staged_cases",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_eval_staged_cases_status", table_name="eval_staged_cases")
    op.drop_index("ix_eval_staged_cases_user_id", table_name="eval_staged_cases")
    op.drop_index(
        "ix_eval_staged_cases_source_conversation",
        table_name="eval_staged_cases",
    )
    op.drop_table("eval_staged_cases")
    op.drop_column("users", "eval_notice_seen_at")
    op.drop_column("users", "eval_data_consent")
