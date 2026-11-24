from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_11_24_0001"
down_revision: str | Sequence[str] | None = "2026_11_23_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_shares",
        sqlalchemy.Column(
            "include_context",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )
    op.alter_column(
        "conversation_shares",
        "include_context",
        server_default=sqlalchemy.text("true"),
    )


def downgrade() -> None:
    op.drop_column("conversation_shares", "include_context")
