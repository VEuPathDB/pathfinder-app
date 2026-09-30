"""A gene set names the answer revision of the strategy root it was read from.

A set read before this revision, or from no strategy, names none.

Revision ID: 2026_09_29_0001
Revises: 2026_09_28_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_09_29_0001"
down_revision: str | Sequence[str] | None = "2026_09_28_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gene_sets",
        sqlalchemy.Column("answer_revision", sqlalchemy.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gene_sets", "answer_revision")
