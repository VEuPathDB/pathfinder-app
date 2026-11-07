from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_11_07_0001"
down_revision: str | Sequence[str] | None = "2026_11_06_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column(
            "memory_enabled",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "memory_enabled")
