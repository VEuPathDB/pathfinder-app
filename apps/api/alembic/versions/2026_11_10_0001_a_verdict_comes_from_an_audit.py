from collections.abc import Sequence

from alembic import op

revision: str = "2026_11_10_0001"
down_revision: str | Sequence[str] | None = "2026_11_09_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM audit_verdicts WHERE origin IN ('lead', 'verification')")
    op.drop_constraint("ck_audit_verdicts_origin", "audit_verdicts", type_="check")
    op.create_check_constraint(
        "ck_audit_verdicts_origin", "audit_verdicts", "origin IN ('auditor', 'review')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_verdicts_origin", "audit_verdicts", type_="check")
    op.create_check_constraint(
        "ck_audit_verdicts_origin",
        "audit_verdicts",
        "origin IN ('auditor', 'lead', 'verification', 'review')",
    )
