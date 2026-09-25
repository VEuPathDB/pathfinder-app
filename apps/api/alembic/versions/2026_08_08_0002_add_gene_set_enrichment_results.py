"""Keep enrichment results on the gene set that was analysed.

Enrichment is a slow WDK round trip. It was computed, returned once, and
thrown away: reopening the workbench showed the set with no analysis and the
researcher had to pay for it again, with nothing saying it had ever been run.

Revision ID: 2026_08_08_0002
Revises: 2026_08_08_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_08_08_0002"
down_revision: str | None = "2026_08_08_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gene_sets",
        sqlalchemy.Column(
            "enrichment_results",
            sqlalchemy.JSON(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("gene_sets", "enrichment_results")
