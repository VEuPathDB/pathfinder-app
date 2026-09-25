"""Add users.supervisor_model_id for per-user orchestrator model override.

Null means "auto" — falls back to the smallest model of the configured default
provider, matching prior behavior.

Revision ID: 2026_04_18_0003
Revises: 2026_04_18_0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_04_18_0003"
down_revision: str | Sequence[str] | None = "2026_04_18_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column(
            "supervisor_model_id", sqlalchemy.String(length=128), nullable=True
        ),
    )


def downgrade() -> None:
    msg = "No backwards compat — this migration is one-way."
    raise NotImplementedError(msg)
