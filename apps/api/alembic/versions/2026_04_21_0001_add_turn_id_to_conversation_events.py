"""Add turn_id to conversation_events for per-turn replay scoping.

Revision ID: 2026_04_21_0001
Revises: 2026_04_20_0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "2026_04_21_0001"
down_revision: str | Sequence[str] | None = "2026_04_20_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_events",
        sqlalchemy.Column("turn_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "conversation_events_conversation_turn_idx",
        "conversation_events",
        ["conversation_id", "turn_id"],
    )


def downgrade() -> None:
    op.drop_index("conversation_events_conversation_turn_idx")
    op.drop_column("conversation_events", "turn_id")
