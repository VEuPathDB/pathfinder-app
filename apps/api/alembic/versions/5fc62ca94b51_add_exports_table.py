"""add_exports_table

Revision ID: 5fc62ca94b51
Revises: c832cac9ff78
Create Date: 2026-04-14 12:18:35.494732

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5fc62ca94b51"
down_revision: str | Sequence[str] | None = "c832cac9ff78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exports",
        sqlalchemy.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sqlalchemy.Column(
            "user_id",
            sqlalchemy.CHAR(36),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("filename", sqlalchemy.String(255), nullable=False),
        sqlalchemy.Column("content_type", sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column("data", sqlalchemy.LargeBinary, nullable=False),
        sqlalchemy.Column(
            "expires_at", sqlalchemy.DateTime(timezone=True), nullable=False
        ),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_exports_expires_at", "exports", ["expires_at"])
    op.create_index("ix_exports_user_id", "exports", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_exports_user_id", table_name="exports")
    op.drop_index("ix_exports_expires_at", table_name="exports")
    op.drop_table("exports")
