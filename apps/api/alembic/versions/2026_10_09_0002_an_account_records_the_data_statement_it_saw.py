"""An account records the version of the data statement it saw.

Revision ID: 2026_10_09_0002
Revises: 2026_10_09_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_10_09_0002"
down_revision: str | Sequence[str] | None = "2026_10_09_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sqlalchemy.Column("data_notice_seen", sqlalchemy.String(32)))
    op.drop_column("users", "eval_notice_seen_at")


def downgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column(
            "eval_notice_seen_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
    )
    op.drop_column("users", "data_notice_seen")
