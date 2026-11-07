from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_11_07_0002"
down_revision: str | Sequence[str] | None = "2026_11_07_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_account_reads",
        sqlalchemy.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sqlalchemy.Column("allowed", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sqlalchemy.Column(
            "account_reads_always",
            sqlalchemy.Boolean(),
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "account_reads_always")
    op.drop_table("conversation_account_reads")
