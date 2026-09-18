"""Record whether PathFinder created a thread's WDK strategy.

A purge deletes a strategy on VEuPathDB only when PathFinder made it there.
Existing rows read false, so a purge leaves every strategy attached before
this column existed alone.

Revision ID: 2026_09_16_0001
Revises: 2026_09_15_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026_09_16_0001"
down_revision: str | Sequence[str] | None = "2026_09_15_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_strategies",
        sa.Column(
            "wdk_strategy_created_here",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversation_strategies", "wdk_strategy_created_here")
