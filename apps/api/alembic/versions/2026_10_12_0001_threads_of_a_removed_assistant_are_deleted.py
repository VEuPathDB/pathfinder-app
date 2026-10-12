"""Delete every thread of the site_help assistant, with its graph state.

Revision ID: 2026_10_12_0001
Revises: 2026_10_09_0002
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_10_12_0001"
down_revision: str | Sequence[str] | None = "2026_10_09_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECKPOINT_DELETES = {
    "checkpoint_writes": "DELETE FROM checkpoint_writes WHERE thread_id IN "
    "(SELECT id::text FROM conversations WHERE assistant_id = 'site_help')",
    "checkpoint_blobs": "DELETE FROM checkpoint_blobs WHERE thread_id IN "
    "(SELECT id::text FROM conversations WHERE assistant_id = 'site_help')",
    "checkpoints": "DELETE FROM checkpoints WHERE thread_id IN "
    "(SELECT id::text FROM conversations WHERE assistant_id = 'site_help')",
}


def upgrade() -> None:
    present = set(sqlalchemy.inspect(op.get_bind()).get_table_names())
    for table, statement in _CHECKPOINT_DELETES.items():
        if table in present:
            op.execute(statement)
    op.execute("DELETE FROM conversations WHERE assistant_id = 'site_help'")


def downgrade() -> None:
    """Irreversible: the deleted threads are not recoverable."""
