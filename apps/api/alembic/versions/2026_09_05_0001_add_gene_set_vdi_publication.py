"""Point a gene set at the VEuPathDB user dataset it was published to.

Publication is opt-in and one-way, so the column is nullable and empty for
every set that was never published.

Revision ID: 2026_09_05_0001
Revises: 2026_08_31_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026_09_05_0001"
down_revision: str | Sequence[str] | None = "2026_08_31_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("gene_sets", sa.Column("vdi_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("gene_sets", "vdi_id")
