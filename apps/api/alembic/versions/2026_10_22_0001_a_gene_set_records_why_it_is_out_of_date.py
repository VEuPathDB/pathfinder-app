"""A gene set records why it no longer holds its strategy's result.

Revision ID: 2026_10_22_0001
Revises: 2026_10_21_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_10_22_0001"
down_revision: str | Sequence[str] | None = "2026_10_21_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gene_sets",
        sqlalchemy.Column("out_of_date", sqlalchemy.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gene_sets", "out_of_date")
