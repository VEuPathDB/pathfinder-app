"""add imported_saved_strategy_ids to conversations

Revision ID: e3a91d22f4c1
Revises: c8a72f1e9d04
Create Date: 2026-04-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3a91d22f4c1"
down_revision: str | Sequence[str] | None = "c8a72f1e9d04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "imported_saved_strategy_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::jsonb"),
        ),
    )
    # Drop the server_default after backfill so application owns the value.
    op.alter_column(
        "conversations",
        "imported_saved_strategy_ids",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("conversations", "imported_saved_strategy_ids")
