"""Attach one open EDA analysis to a chat thread.

A thread gets a row only while it holds an open EDA analysis. The upstream EDA
user service owns the document, so the row carries the reference and the
mutation counter, never the descriptor.

Revision ID: 2026_08_28_0002
Revises: 2026_08_28_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_08_28_0002"
down_revision: str | Sequence[str] | None = "2026_08_28_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_analyses",
        sqlalchemy.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sqlalchemy.Column("site_id", sqlalchemy.String(50), nullable=False),
        sqlalchemy.Column("dataset_id", sqlalchemy.String(100), nullable=False),
        sqlalchemy.Column("analysis_id", sqlalchemy.String(100), nullable=False),
        sqlalchemy.Column(
            "revision", sqlalchemy.Integer(), nullable=False, server_default="0"
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_analyses_dataset_id",
        "conversation_analyses",
        ["dataset_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_analyses_dataset_id",
        table_name="conversation_analyses",
    )
    op.drop_table("conversation_analyses")
