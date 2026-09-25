"""Record with each snapshot the saved mark of the WDK strategy it names.

A restore writes the snapshot's strategy id back, so the snapshot has to carry
that id's saved mark. Existing snapshots read false.

Revision ID: 2026_09_16_0003
Revises: 2026_09_16_0002
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_09_16_0003"
down_revision: str | Sequence[str] | None = "2026_09_16_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_revisions",
        sqlalchemy.Column(
            "is_saved",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_revisions", "is_saved")
