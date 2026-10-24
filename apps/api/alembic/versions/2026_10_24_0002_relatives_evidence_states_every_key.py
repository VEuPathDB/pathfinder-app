from collections.abc import Sequence

from alembic import op

revision: str = "2026_10_24_0002"
down_revision: str | Sequence[str] | None = "2026_10_23_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE audit_evidence SET payload = "
        """'{"relativeLengths": {}, "relativesTier": null, "side": null, """
        """"referenceOrganism": null}'::jsonb || payload """
        "WHERE kind = 'relatives' AND payload IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE audit_evidence SET payload = "
        "payload - 'relativeLengths' - 'relativesTier' "
        "WHERE kind = 'relatives' AND payload IS NOT NULL"
    )
