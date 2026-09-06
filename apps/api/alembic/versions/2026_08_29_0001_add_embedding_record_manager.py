"""Widen the memory store's vectors to the current embedding dimension.

The store's rows are dropped because a 512-wide vector cannot be read as a
1024-wide one; the operator re-embeds them.

Revision ID: 2026_08_29_0001
Revises: 2026_08_28_0002
"""

from collections.abc import Sequence

from alembic import op

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
    op.execute(_WIDEN_STORE_VECTORS)


def downgrade() -> None:
    """The column keeps the wider type: the dropped vectors cannot be restored."""
