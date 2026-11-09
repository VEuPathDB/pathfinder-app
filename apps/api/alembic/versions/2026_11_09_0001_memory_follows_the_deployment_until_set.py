from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_11_09_0001"
down_revision: str | Sequence[str] | None = "2026_11_07_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "memory_enabled", nullable=True, server_default=None)
    op.execute("UPDATE users SET memory_enabled = NULL")


def downgrade() -> None:
    op.execute("UPDATE users SET memory_enabled = true WHERE memory_enabled IS NULL")
    op.alter_column(
        "users",
        "memory_enabled",
        nullable=False,
        server_default=sqlalchemy.text("true"),
    )
