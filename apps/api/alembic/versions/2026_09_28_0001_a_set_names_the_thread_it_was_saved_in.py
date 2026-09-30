"""A gene set and a control set name the thread they were saved in.

A set saved outside a thread, or before this revision, names none. A set
outlives its thread, so deleting the thread empties the column.

Revision ID: 2026_09_28_0001
Revises: 2026_09_24_0004
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "2026_09_28_0001"
down_revision: str | Sequence[str] | None = "2026_09_24_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("gene_sets", "control_sets")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sqlalchemy.Column(
                "conversation_id",
                UUID(as_uuid=True),
                sqlalchemy.ForeignKey(
                    "conversations.id",
                    name=f"fk_{table}_conversation_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_conversation_id", table, ["conversation_id"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_conversation_id", table_name=table)
        op.drop_column(table, "conversation_id")
