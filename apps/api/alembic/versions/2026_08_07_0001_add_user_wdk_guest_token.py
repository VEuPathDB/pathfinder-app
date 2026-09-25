"""add_user_wdk_guest_token

Revision ID: 2026_08_07_0001
Revises: 2026_06_24_0001
Create Date: 2026-08-07 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_08_07_0001"
down_revision: str | Sequence[str] | None = "2026_06_24_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column("wdk_guest_token", sqlalchemy.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "wdk_guest_token")
