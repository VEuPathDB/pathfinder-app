"""add_background_tasks_and_events

Revision ID: b97ba9130ec3
Revises: 3efc8ac5248a
Create Date: 2026-04-14 13:57:14.195849

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "b97ba9130ec3"
down_revision: str | Sequence[str] | None = "3efc8ac5248a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create background_tasks, task_progress, and chat_events."""
    op.create_table(
        "background_tasks",
        sqlalchemy.Column("id", UUID(as_uuid=True), primary_key=True),
        sqlalchemy.Column(
            "chat_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column(
            "user_id",
            sqlalchemy.CHAR(36),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("tool_name", sqlalchemy.String(128), nullable=False),
        sqlalchemy.Column(
            "status", sqlalchemy.String(32), nullable=False, server_default="pending"
        ),
        sqlalchemy.Column("args", JSONB, nullable=False),
        sqlalchemy.Column("result", JSONB, nullable=True),
        sqlalchemy.Column("error", sqlalchemy.Text, nullable=True),
        sqlalchemy.Column(
            "estimated_duration_seconds",
            sqlalchemy.Integer,
            nullable=False,
            server_default="60",
        ),
        sqlalchemy.Column(
            "started_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.Column(
            "completed_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_background_tasks_chat_id", "background_tasks", ["chat_id"])
    op.create_index("ix_background_tasks_user_id", "background_tasks", ["user_id"])

    op.create_table(
        "task_progress",
        sqlalchemy.Column(
            "id", sqlalchemy.Integer, primary_key=True, autoincrement=True
        ),
        sqlalchemy.Column(
            "task_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("background_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("percent", sqlalchemy.Float, nullable=False),
        sqlalchemy.Column("message", sqlalchemy.String(500), nullable=False),
        sqlalchemy.Column("data", JSONB, nullable=True),
        sqlalchemy.Column(
            "emitted_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_task_progress_task_id", "task_progress", ["task_id"])

    op.create_table(
        "chat_events",
        sqlalchemy.Column(
            "id", sqlalchemy.Integer, primary_key=True, autoincrement=True
        ),
        sqlalchemy.Column(
            "chat_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("chats.id", ondelete="CASCADE"),
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
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_chat_events_chat_id", "chat_events", ["chat_id"])
    op.create_index("ix_chat_events_task_id", "chat_events", ["task_id"])


def downgrade() -> None:
    """Drop chat_events, task_progress, and background_tasks."""
    op.drop_index("ix_chat_events_task_id", table_name="chat_events")
    op.drop_index("ix_chat_events_chat_id", table_name="chat_events")
    op.drop_table("chat_events")
    op.drop_index("ix_task_progress_task_id", table_name="task_progress")
    op.drop_table("task_progress")
    op.drop_index("ix_background_tasks_user_id", table_name="background_tasks")
    op.drop_index("ix_background_tasks_chat_id", table_name="background_tasks")
    op.drop_table("background_tasks")
