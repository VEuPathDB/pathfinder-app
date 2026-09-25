"""add_memory_tombstones

Revision ID: 29b8e0c301b3
Revises: 5fc62ca94b51
Create Date: 2026-04-14 12:49:13.185516

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29b8e0c301b3"
down_revision: str | Sequence[str] | None = "5fc62ca94b51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_tombstones",
        sqlalchemy.Column(
            "id",
            sqlalchemy.Integer,
            primary_key=True,
            autoincrement=True,
        ),
        sqlalchemy.Column(
            "user_id",
            sqlalchemy.CHAR(36),
            sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("kind", sqlalchemy.String(32), nullable=False),
        sqlalchemy.Column("content_hash", sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column(
            "reason",
            sqlalchemy.String(32),
            nullable=False,
            server_default="user_deleted",
        ),
        sqlalchemy.Column(
            "deleted_at",
            sqlalchemy.DateTime(timezone=True),
            server_default=sqlalchemy.func.now(),
            nullable=False,
        ),
        sqlalchemy.UniqueConstraint(
            "user_id",
            "kind",
            "content_hash",
            name="uq_tombstones_user_kind_hash",
        ),
    )
    op.create_index(
        "ix_memory_tombstones_user_id",
        "memory_tombstones",
        ["user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memory_tombstones_user_id", table_name="memory_tombstones")
    op.drop_table("memory_tombstones")
