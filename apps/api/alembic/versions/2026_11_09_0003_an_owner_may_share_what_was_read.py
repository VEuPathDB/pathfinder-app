from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_11_09_0003"
down_revision: str | Sequence[str] | None = "2026_11_09_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_shares",
        sqlalchemy.Column(
            "include_account_reads",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversation_shares", "include_account_reads")
