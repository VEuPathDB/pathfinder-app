"""drop_user_wdk_guest_token

Revision ID: 2026_08_19_0002
Revises: 2026_08_19_0001
Create Date: 2026-08-19 00:00:00.000000

VEuPathDB serves the WDK service to registered users only, so a stored guest
token names an identity the service refuses. The downgrade puts the nullable
column back empty; the tokens themselves are not recoverable.
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_08_19_0002"
down_revision: str | Sequence[str] | None = "2026_08_19_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "wdk_guest_token")


def downgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column("wdk_guest_token", sqlalchemy.Text(), nullable=True),
    )
