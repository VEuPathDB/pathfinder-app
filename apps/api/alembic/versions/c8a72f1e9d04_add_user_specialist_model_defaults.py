"""add_user_specialist_model_defaults

Revision ID: c8a72f1e9d04
Revises: d1a3e9b48f02
Create Date: 2026-04-26 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8a72f1e9d04"
down_revision: str | Sequence[str] | None = "d1a3e9b48f02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column(
            "specialist_model_defaults",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "specialist_model_defaults")
