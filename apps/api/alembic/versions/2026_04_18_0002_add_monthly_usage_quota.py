"""Add per-user monthly USD quota: users.monthly_cost_limit_usd + monthly_usage table.

Revision ID: 2026_04_18_0002
Revises: 2026_04_18_0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_04_18_0002"
down_revision: str | Sequence[str] | None = "2026_04_18_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column("monthly_cost_limit_usd", sqlalchemy.Float(), nullable=True),
    )

    op.create_table(
        "monthly_usage",
        sqlalchemy.Column("id", sqlalchemy.CHAR(36), primary_key=True),
        sqlalchemy.Column(
            "user_id",
            sqlalchemy.CHAR(36),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("period_start", sqlalchemy.Date(), nullable=False),
        sqlalchemy.Column(
            "total_cost_usd",
            sqlalchemy.Numeric(12, 6),
            nullable=False,
            server_default=sqlalchemy.text("0"),
        ),
        sqlalchemy.Column(
            "total_tokens",
            sqlalchemy.BigInteger(),
            nullable=False,
            server_default=sqlalchemy.text("0"),
        ),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.UniqueConstraint(
            "user_id", "period_start", name="monthly_usage_user_period_key"
        ),
    )
    op.create_index(
        "monthly_usage_user_idx",
        "monthly_usage",
        ["user_id"],
    )


def downgrade() -> None:
    msg = "No backwards compat — this migration is one-way."
    raise NotImplementedError(msg)
