"""Add scratchpad_notes and scratchpad_compactions tables.

Scratchpad is conversation-scoped working memory for phase agents: each
note has a title, summary, and markdown body; a GENERATED ALWAYS tsvector
column powers FTS for search_notes(); tags are JSONB for flexible tagging
without a join table. The scratchpad_compactions table is the audit log
for LLM-driven compaction runs triggered on verification done.

Revision ID: 2026_04_20_0001
Revises: 2026_04_18_0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision: str = "2026_04_20_0001"
down_revision: str | Sequence[str] | None = "2026_04_18_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scratchpad_notes",
        sqlalchemy.Column("id", sqlalchemy.Text(), primary_key=True),
        sqlalchemy.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("title", sqlalchemy.Text(), nullable=False),
        sqlalchemy.Column("summary", sqlalchemy.Text(), nullable=False),
        sqlalchemy.Column("body", sqlalchemy.Text(), nullable=False),
        sqlalchemy.Column(
            "tags",
            JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::jsonb"),
        ),
        sqlalchemy.Column(
            "pinned",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
        sqlalchemy.Column("body_tokens", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column(
            "fts",
            TSVECTOR(),
            sqlalchemy.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') "
                "|| setweight(to_tsvector('english', coalesce(summary, '')), 'B') "
                "|| setweight(to_tsvector('english', coalesce(body, '')), 'C')",
                persisted=True,
            ),
            nullable=False,
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "scratchpad_notes_conv_idx",
        "scratchpad_notes",
        [
            "conversation_id",
            sqlalchemy.text("pinned DESC"),
            sqlalchemy.text("created_at DESC"),
        ],
    )
    op.create_index(
        "scratchpad_notes_fts_idx",
        "scratchpad_notes",
        ["fts"],
        postgresql_using="gin",
    )
    op.create_index(
        "scratchpad_notes_tags_idx",
        "scratchpad_notes",
        ["tags"],
        postgresql_using="gin",
        postgresql_ops={"tags": "jsonb_path_ops"},
    )

    op.create_table(
        "scratchpad_compactions",
        sqlalchemy.Column(
            "id",
            sqlalchemy.BigInteger(),
            sqlalchemy.Identity(always=False),
            primary_key=True,
        ),
        sqlalchemy.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "triggered_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.Column("before_count", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("after_count", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("before_tokens", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("after_tokens", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("model_id", sqlalchemy.Text(), nullable=False),
        sqlalchemy.Column(
            "cost_usd",
            sqlalchemy.Numeric(precision=12, scale=6),
            nullable=False,
            server_default=sqlalchemy.text("0"),
        ),
        sqlalchemy.Column("trigger_reason", sqlalchemy.Text(), nullable=False),
        sqlalchemy.CheckConstraint(
            "trigger_reason IN ('count', 'tokens', 'both')",
            name="ck_scratchpad_compactions_trigger_reason",
        ),
    )
    op.create_index(
        "scratchpad_compactions_conv_idx",
        "scratchpad_compactions",
        ["conversation_id", sqlalchemy.text("triggered_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "scratchpad_compactions_conv_idx", table_name="scratchpad_compactions"
    )
    op.drop_table("scratchpad_compactions")
    op.drop_index("scratchpad_notes_tags_idx", table_name="scratchpad_notes")
    op.drop_index("scratchpad_notes_fts_idx", table_name="scratchpad_notes")
    op.drop_index("scratchpad_notes_conv_idx", table_name="scratchpad_notes")
    op.drop_table("scratchpad_notes")
