"""Add conversations.supervisor_model_id for per-chat orchestrator override.

Null = fall back to users.supervisor_model_id; then to auto. One precedence
chain drives supervisor model resolution at turn time.

Revision ID: 2026_04_18_0004
Revises: 2026_04_18_0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_04_18_0004"
down_revision: str | Sequence[str] | None = "2026_04_18_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "supervisor_model_id", sqlalchemy.String(length=128), nullable=True
        ),
    )


def downgrade() -> None:
    msg = "No backwards compat — this migration is one-way."
    raise NotImplementedError(msg)
