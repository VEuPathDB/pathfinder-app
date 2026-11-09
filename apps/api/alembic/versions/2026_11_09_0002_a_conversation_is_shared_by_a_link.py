from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_11_09_0002"
down_revision: str | Sequence[str] | None = "2026_11_09_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_shares",
        sqlalchemy.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sqlalchemy.Column("token", sqlalchemy.String(64), nullable=False, unique=True),
        sqlalchemy.Column("public", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column("password_hash", sqlalchemy.String(64), nullable=True),
        sqlalchemy.Column("allow_copy", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.CheckConstraint(
            "public OR password_hash IS NOT NULL",
            name="ck_conversation_shares_private_has_password",
        ),
    )


def downgrade() -> None:
    op.drop_table("conversation_shares")
