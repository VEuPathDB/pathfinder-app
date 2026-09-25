"""Record with each snapshot who created the WDK strategy it names.

A restore writes the snapshot's strategy id back, so the snapshot has to carry
that id's provenance. Existing snapshots read false.

Revision ID: 2026_09_16_0002
Revises: 2026_09_16_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_09_16_0002"
down_revision: str | Sequence[str] | None = "2026_09_16_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_revisions",
        sqlalchemy.Column(
            "wdk_strategy_created_here",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_revisions", "wdk_strategy_created_here")
