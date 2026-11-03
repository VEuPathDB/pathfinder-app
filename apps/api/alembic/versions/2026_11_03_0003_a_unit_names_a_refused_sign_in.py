from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_11_03_0003"
down_revision: str | Sequence[str] | None = "2026_11_03_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("audit_genomes", "audit_findings", "audit_evidence"):
        op.add_column(
            table,
            sqlalchemy.Column(
                "refused_by_sign_in",
                sqlalchemy.Boolean(),
                nullable=False,
                server_default=sqlalchemy.text("false"),
            ),
        )


def downgrade() -> None:
    for table in ("audit_genomes", "audit_findings", "audit_evidence"):
        op.drop_column(table, "refused_by_sign_in")
