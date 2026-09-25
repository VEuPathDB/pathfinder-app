"""Drop the columns only the workbench wrote.

A gene set no longer records a set operation or an enrichment, an experiment no
longer names a gene set, a batch or a benchmark, and a thread no longer names an
experiment.
The downgrade restores each column as the migration that added it defined it,
empty.

Revision ID: 2026_09_24_0003
Revises: 2026_09_24_0002
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_09_24_0003"
down_revision: str | Sequence[str] | None = "2026_09_24_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXPERIMENT_INDEXES = {
    "ix_experiments_batch_id": "batch_id",
    "ix_experiments_benchmark_id": "benchmark_id",
    "ix_experiments_gene_set_id": "gene_set_id",
}


def upgrade() -> None:
    op.drop_column("gene_sets", "enrichment_results")
    op.drop_column("gene_sets", "parent_set_ids")
    op.drop_column("gene_sets", "operation")
    for index, column in _EXPERIMENT_INDEXES.items():
        op.drop_index(index, table_name="experiments")
        op.drop_column("experiments", column)
    op.drop_column("conversation_strategies", "experiment_id")


def downgrade() -> None:
    op.add_column(
        "conversation_strategies",
        sqlalchemy.Column(
            "experiment_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("experiments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    for index, column in _EXPERIMENT_INDEXES.items():
        op.add_column(
            "experiments",
            sqlalchemy.Column(column, sqlalchemy.String(length=50), nullable=True),
        )
        op.create_index(index, "experiments", [column], unique=False)
    op.add_column(
        "gene_sets",
        sqlalchemy.Column("operation", sqlalchemy.String(length=20), nullable=True),
    )
    op.add_column(
        "gene_sets",
        sqlalchemy.Column(
            "parent_set_ids", sqlalchemy.JSON(), nullable=False, server_default="[]"
        ),
    )
    op.alter_column("gene_sets", "parent_set_ids", server_default=None)
    op.add_column(
        "gene_sets",
        sqlalchemy.Column(
            "enrichment_results",
            sqlalchemy.JSON(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::json"),
        ),
    )
