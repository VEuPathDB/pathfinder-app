"""add chat_turn_cancellations table

Revision ID: 2026_05_04_0001
Revises: f1b8d4a92c70
Create Date: 2026-05-04 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "2026_05_04_0001"
down_revision: str | Sequence[str] | None = "f1b8d4a92c70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_turn_cancellations",
        sqlalchemy.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sqlalchemy.Column("turn_id", UUID(as_uuid=True), nullable=False),
        sqlalchemy.Column(
            "requested_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.PrimaryKeyConstraint(
            "conversation_id",
            "turn_id",
            name="pk_chat_turn_cancellations",
        ),
        sqlalchemy.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_turn_cancellations")
