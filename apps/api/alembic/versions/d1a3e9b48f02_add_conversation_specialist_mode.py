"""add_conversation_specialist_mode

Revision ID: d1a3e9b48f02
Revises: 5fc62ca94b51
Create Date: 2026-04-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1a3e9b48f02"
down_revision: str | Sequence[str] | None = "4ed47a46a8b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sqlalchemy.Column("specialist_mode", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "specialist_mode")
