"""Delete every job in a final state, with its events.

Revision ID: 2026_10_09_0001
Revises: 2026_10_04_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "2026_10_09_0001"
down_revision: str | Sequence[str] | None = "2026_10_04_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM procrastinate_jobs "
        "WHERE status IN ('succeeded', 'failed', 'cancelled', 'aborted')"
    )


def downgrade() -> None:
    pass
