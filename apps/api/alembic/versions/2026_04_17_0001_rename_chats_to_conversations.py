"""Rename chats → conversations; drop and recreate cleanly.

Revision ID: 2026_04_17_0001
Revises: 2026_04_15_0001
Create Date: 2026-04-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pathfinder.persistence.models import GUID

revision: str = "2026_04_17_0001"
down_revision: str | Sequence[str] | None = "2026_04_15_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS checkpoint_writes CASCADE")
    op.execute("DROP TABLE IF EXISTS checkpoint_blobs CASCADE")
    op.execute("DROP TABLE IF EXISTS checkpoint_migrations CASCADE")
    op.execute("DROP TABLE IF EXISTS checkpoints CASCADE")

    op.execute("DROP TABLE IF EXISTS store CASCADE")
    op.execute("DROP TABLE IF EXISTS store_migrations CASCADE")
    op.execute("DROP TABLE IF EXISTS store_vectors CASCADE")
    op.execute("DROP TABLE IF EXISTS vector_migrations CASCADE")

    op.execute("DROP TABLE IF EXISTS checkpoint_labels CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_events CASCADE")
    op.execute("DROP TABLE IF EXISTS task_progress CASCADE")
    op.execute("DROP TABLE IF EXISTS background_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS memory_tombstones CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chats CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")

    op.create_table(
        "conversations",
        sqlalchemy.Column("id", UUID(as_uuid=True), primary_key=True),
        sqlalchemy.Column(
            "user_id",
            GUID(),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "site_id", sqlalchemy.String(50), nullable=False, server_default=""
        ),
        sqlalchemy.Column(
            "name", sqlalchemy.String(255), nullable=False, server_default=""
        ),
        sqlalchemy.Column("record_type", sqlalchemy.String(100), nullable=True),
        sqlalchemy.Column("wdk_strategy_id", sqlalchemy.Integer, nullable=True),
        sqlalchemy.Column(
            "is_saved",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
        sqlalchemy.Column("pipeline", JSONB, nullable=True),
        sqlalchemy.Column(
            "step_count",
            sqlalchemy.Integer,
            nullable=False,
            server_default="0",
        ),
        sqlalchemy.Column("plan", JSONB, nullable=False, server_default="{}"),
        sqlalchemy.Column("estimated_size", sqlalchemy.Integer, nullable=True),
        sqlalchemy.Column(
            "gene_set_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("gene_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sqlalchemy.Column(
            "gene_set_auto_imported",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
        sqlalchemy.Column(
            "experiment_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("experiments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sqlalchemy.Column(
            "dismissed_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversations_user_site",
        "conversations",
        ["user_id", "site_id"],
    )
    op.create_index(
        "ix_conversations_wdk_strategy_id",
        "conversations",
        ["wdk_strategy_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("wdk_strategy_id IS NOT NULL"),
    )

    op.create_table(
        "messages",
        sqlalchemy.Column("id", UUID(as_uuid=True), primary_key=True),
        sqlalchemy.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("role", sqlalchemy.String, nullable=False),
        sqlalchemy.Column("parts", JSONB, nullable=False, server_default="[]"),
        sqlalchemy.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
        sqlalchemy.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
    )
    op.create_index(
        "messages_conversation_id_created_at_idx",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "background_tasks",
        sqlalchemy.Column("id", UUID(as_uuid=True), primary_key=True),
        sqlalchemy.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "user_id",
            GUID(),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("tool_name", sqlalchemy.Text, nullable=False),
        sqlalchemy.Column("status", sqlalchemy.Text, nullable=False),
        sqlalchemy.Column("args", JSONB, nullable=False, server_default="{}"),
        sqlalchemy.Column("result", JSONB, nullable=True),
        sqlalchemy.Column("error", sqlalchemy.Text, nullable=True),
        sqlalchemy.Column(
            "estimated_duration_seconds",
            sqlalchemy.Integer,
            nullable=False,
            server_default="0",
        ),
        sqlalchemy.Column(
            "started_at",
            sqlalchemy.DateTime(timezone=True),
            nullable=True,
        ),
        sqlalchemy.Column(
            "completed_at",
            sqlalchemy.DateTime(timezone=True),
            nullable=True,
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "bg_tasks_conversation_idx",
        "background_tasks",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "task_progress",
        sqlalchemy.Column(
            "id",
            sqlalchemy.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
        sqlalchemy.Column(
            "task_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("background_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("percent", sqlalchemy.Float, nullable=False),
        sqlalchemy.Column(
            "message", sqlalchemy.Text, nullable=False, server_default=""
        ),
        sqlalchemy.Column("data", JSONB, nullable=True),
        sqlalchemy.Column(
            "emitted_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "task_progress_task_idx",
        "task_progress",
        ["task_id", "emitted_at"],
    )

    op.create_table(
        "conversation_events",
        sqlalchemy.Column(
            "id",
            sqlalchemy.Integer,
            primary_key=True,
            autoincrement=True,
        ),
        sqlalchemy.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "task_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("background_tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sqlalchemy.Column("chunk", JSONB, nullable=False),
        sqlalchemy.Column(
            "emitted_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "conversation_events_conversation_id_idx",
        "conversation_events",
        ["conversation_id"],
    )
    op.create_index(
        "conversation_events_task_id_idx",
        "conversation_events",
        ["task_id"],
    )

    op.create_table(
        "checkpoint_labels",
        sqlalchemy.Column("thread_id", sqlalchemy.Text, nullable=False),
        sqlalchemy.Column("checkpoint_id", sqlalchemy.Text, nullable=False),
        sqlalchemy.Column("user_id", UUID(as_uuid=True), nullable=False),
        sqlalchemy.Column("label", sqlalchemy.Text, nullable=True),
        sqlalchemy.Column(
            "pinned",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
        sqlalchemy.PrimaryKeyConstraint("thread_id", "checkpoint_id", "user_id"),
    )
    op.create_index(
        "checkpoint_labels_thread_idx",
        "checkpoint_labels",
        ["thread_id"],
    )

    op.create_table(
        "memory_tombstones",
        sqlalchemy.Column(
            "id",
            sqlalchemy.Integer,
            primary_key=True,
            autoincrement=True,
        ),
        sqlalchemy.Column(
            "user_id",
            GUID(),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("kind", sqlalchemy.String(32), nullable=False),
        sqlalchemy.Column("content_hash", sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column(
            "reason",
            sqlalchemy.String(32),
            nullable=False,
            server_default="user_deleted",
        ),
        sqlalchemy.Column(
            "deleted_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.text("now()"),
            nullable=False,
        ),
        sqlalchemy.UniqueConstraint(
            "user_id",
            "kind",
            "content_hash",
            name="uq_tombstones_user_kind_hash",
        ),
    )
    op.create_index(
        "ix_memory_tombstones_user_id",
        "memory_tombstones",
        ["user_id"],
    )


def downgrade() -> None:
    msg = "No backwards compat — this migration is one-way."
    raise NotImplementedError(msg)
