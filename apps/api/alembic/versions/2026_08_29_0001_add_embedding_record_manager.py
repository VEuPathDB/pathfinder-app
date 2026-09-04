"""Hold every embedding in Postgres, addressed by the text that produced it.

The vectors move from per-site files to two tables, and the memory store's
column widens to the new model's dimension. The store's rows are dropped
because a 512-wide vector cannot be read as a 1024-wide one; the operator
re-embeds them.

Revision ID: 2026_08_29_0001
Revises: 2026_08_28_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "2026_08_29_0001"
down_revision: str | Sequence[str] | None = "2026_08_28_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIMENSIONS = 1024

# The memory store's tables are created by the LangGraph store, not by alembic,
# so a database that never held a memory has nothing to widen.
_WIDEN_STORE_VECTORS = f"""
DO $$
BEGIN
    IF to_regclass('public.store_vectors') IS NOT NULL THEN
        TRUNCATE TABLE store_vectors;
        ALTER TABLE store_vectors
            ALTER COLUMN embedding TYPE vector({_EMBEDDING_DIMENSIONS});
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "embedding_vectors",
        sa.Column("model", sa.String(64), primary_key=True),
        sa.Column("content_hash", sa.String(64), primary_key=True),
        sa.Column("embedding", VECTOR(_EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "embedding_index_entries",
        sa.Column("index_id", sa.String(128), primary_key=True),
        sa.Column("entry_id", sa.String(256), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_embedding_index_entries_index_id",
        "embedding_index_entries",
        ["index_id"],
    )
    op.execute(_WIDEN_STORE_VECTORS)


def downgrade() -> None:
    """Irreversible: the dropped memory vectors cannot be reconstructed."""
    op.drop_index(
        "ix_embedding_index_entries_index_id",
        table_name="embedding_index_entries",
    )
    op.drop_table("embedding_index_entries")
    op.drop_table("embedding_vectors")
