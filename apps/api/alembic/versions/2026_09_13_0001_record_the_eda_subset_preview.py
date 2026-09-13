"""Record on the thread's analysis that a preview counted its subset.

The export of an EDA subset follows the count, and the count belongs to the
analysis rather than to the message that ran it.

Revision ID: 2026_09_13_0001
Revises: 2026_09_05_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026_09_13_0001"
down_revision: str | Sequence[str] | None = "2026_09_05_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_analyses",
        sa.Column(
            "subset_previewed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("conversation_analyses", "subset_previewed")
