"""Conversation forks: parent_conversation_id + parent_message_id.

Forking copies messages from a source conversation up through a chosen
assistant message into a brand-new conversation, preserving the parent chain
for the sidebar tree. ``parent_message_id`` is the turn the user branched at;
``parent_conversation_id`` is the source chat.

Revision ID: 2026_04_18_0005
Revises: 2026_04_18_0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "2026_04_18_0005"
down_revision: str | Sequence[str] | None = "2026_04_18_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "parent_conversation_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "parent_message_id",
            UUID(as_uuid=True),
            sqlalchemy.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_parent_conversation_id",
        "conversations",
        ["parent_conversation_id"],
    )


def downgrade() -> None:
    msg = "No backwards compat — this migration is one-way."
    raise NotImplementedError(msg)
