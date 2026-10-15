"""Record, for each gene of a saved set, the gene and the site that holds it.

A set saved on a genomics site holds that site's genes, so its rows are filled.
A portal or OrthoMCL set has no record of its genes' sites, so it stays empty.

Revision ID: 2026_10_15_0001
Revises: 2026_10_12_0001
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_10_15_0001"
down_revision: str | Sequence[str] | None = "2026_10_12_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENOMICS_SETS_HOLD_THEIR_SITES_GENES = """
UPDATE gene_sets SET homes = (
    SELECT coalesce(
        json_object_agg(gene, json_build_object('geneId', gene, 'siteId', site_id)),
        '{}'::json
    )
    FROM json_array_elements_text(gene_ids) AS gene
)
WHERE site_id NOT IN ('veupathdb', 'orthomcl')
  AND coalesce(record_type, 'transcript') IN ('transcript', 'gene')
"""


def upgrade() -> None:
    op.add_column(
        "gene_sets",
        sqlalchemy.Column(
            "homes", sqlalchemy.JSON(), nullable=False, server_default="{}"
        ),
    )
    op.execute(_GENOMICS_SETS_HOLD_THEIR_SITES_GENES)


def downgrade() -> None:
    op.drop_column("gene_sets", "homes")
