"""add_conversation_assistant_id

Revision ID: 2026_08_22_0001
Revises: 2026_08_21_0002
Create Date: 2026-08-22 00:00:00.000000

Which assistant answers a thread. Every existing thread is PathFinder's, and
a thread never changes assistant, so the column is additive with a default.
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_08_22_0001"
down_revision: str | Sequence[str] | None = "2026_08_21_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_ASSISTANT_ID = "pathfinder"


def upgrade() -> None:
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "assistant_id",
            sqlalchemy.String(length=64),
            nullable=False,
            server_default=_DEFAULT_ASSISTANT_ID,
        ),
    )
    op.create_index(
        "ix_conversations_assistant_id",
        "conversations",
        ["assistant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_assistant_id", table_name="conversations")
    op.drop_column("conversations", "assistant_id")
