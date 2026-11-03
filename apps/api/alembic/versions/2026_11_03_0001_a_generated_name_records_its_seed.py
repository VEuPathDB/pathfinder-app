"""A generated strategy name records its seed: each step's parameter wire values.

A name stored with only its steps carries no seed, so it reads as a person
chose it and is never regenerated.

Revision ID: 2026_11_03_0001
Revises: 2026_10_30_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_11_03_0001"
down_revision: str | Sequence[str] | None = "2026_10_30_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_strategies",
        sqlalchemy.Column("generated_name_seed", postgresql.JSONB(), nullable=True),
    )
    op.drop_column("conversation_strategies", "generated_name_steps")


def downgrade() -> None:
    op.add_column(
        "conversation_strategies",
        sqlalchemy.Column("generated_name_steps", postgresql.JSONB(), nullable=True),
    )
    op.execute(
        "UPDATE conversation_strategies SET generated_name_steps = COALESCE("
        "(SELECT jsonb_agg(step ORDER BY step) "
        "FROM jsonb_object_keys(generated_name_seed) AS step), '[]'::jsonb) "
        "WHERE generated_name_seed IS NOT NULL"
    )
    op.drop_column("conversation_strategies", "generated_name_seed")
