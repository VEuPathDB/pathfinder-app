"""A generated strategy name records the steps it was written over.

Null means a person chose the name. Existing rows read null, so the upgrade
regenerates no name.

Revision ID: 2026_10_04_0001
Revises: 2026_09_29_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_10_04_0001"
down_revision: str | Sequence[str] | None = "2026_09_29_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_strategies",
        sqlalchemy.Column("generated_name_steps", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_strategies", "generated_name_steps")
