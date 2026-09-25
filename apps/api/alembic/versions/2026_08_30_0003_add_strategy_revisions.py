"""Give a thread's strategy a revision history.

Fork and revert read the strategy as it stood at a chosen message. Without a
per-revision snapshot both operations can only copy the latest AST.

Revision ID: 2026_08_30_0003
Revises: 2026_08_30_0002
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_08_30_0003"
down_revision: str | Sequence[str] | None = "2026_08_30_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_revisions",
        sqlalchemy.Column(
            "id", sqlalchemy.BigInteger(), sqlalchemy.Identity(), primary_key=True
        ),
        sqlalchemy.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("revision", sqlalchemy.String(length=64), nullable=False),
        sqlalchemy.Column("record_type", sqlalchemy.String(length=100), nullable=True),
        sqlalchemy.Column(
            "strategy_ast",
            postgresql.JSONB(astext_type=sqlalchemy.Text()),
            nullable=False,
            server_default="{}",
        ),
        sqlalchemy.Column(
            "step_count", sqlalchemy.Integer(), nullable=False, server_default="0"
        ),
        sqlalchemy.Column("wdk_strategy_id", sqlalchemy.Integer(), nullable=True),
        sqlalchemy.Column("name", sqlalchemy.String(length=255), nullable=True),
        sqlalchemy.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_strategy_revisions_conversation_created",
        "strategy_revisions",
        ["conversation_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_revisions_conversation_created",
        table_name="strategy_revisions",
    )
    op.drop_table("strategy_revisions")
