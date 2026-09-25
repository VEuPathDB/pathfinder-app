"""Add users.pipeline_config for server-side per-phase model preferences.

JSONB shape: ``{provider, tier, phases: {<PhaseName>: {modelId, reasoningEffort}}}``.
``NULL`` means "use phase-agent defaults" — backward compatible with existing rows.

Revision ID: 2026_04_22_0001
Revises: 2026_04_21_0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "2026_04_22_0001"
down_revision: str | Sequence[str] | None = "2026_04_21_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column("pipeline_config", JSONB(), nullable=True),
    )


def downgrade() -> None:
    msg = "No backwards compat — this migration is one-way."
    raise NotImplementedError(msg)
