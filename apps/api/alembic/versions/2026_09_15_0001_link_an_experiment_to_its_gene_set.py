"""Point an experiment at the workbench gene set it evaluated.

An experiment can start from a strategy instead of a set, and rows exist that
predate the pointer, so the column is nullable. It is indexed because the set's
view reads its experiments by it.

Revision ID: 2026_09_15_0001
Revises: 2026_09_13_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026_09_15_0001"
down_revision: str | Sequence[str] | None = "2026_09_13_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "experiments", sa.Column("gene_set_id", sa.String(length=50), nullable=True)
    )
    op.create_index("ix_experiments_gene_set_id", "experiments", ["gene_set_id"])


def downgrade() -> None:
    op.drop_index("ix_experiments_gene_set_id", table_name="experiments")
    op.drop_column("experiments", "gene_set_id")
