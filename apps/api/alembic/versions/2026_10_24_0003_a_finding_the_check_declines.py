"""An audit finding the check declines is stored declined.

Revision ID: 2026_10_24_0003
Revises: 2026_10_24_0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "2026_10_24_0003"
down_revision: str | Sequence[str] | None = "2026_10_24_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = (
    "'screened', 'unsampled', 'trying', 'confirmed', 'failed', 'unreached', 'unread'"
)


def upgrade() -> None:
    op.drop_constraint("ck_audit_findings_status", "audit_findings", type_="check")
    op.create_check_constraint(
        "ck_audit_findings_status",
        "audit_findings",
        f"status IN ({_STATUSES}, 'declined')",
    )


def downgrade() -> None:
    op.execute("UPDATE audit_findings SET status = 'failed' WHERE status = 'declined'")
    op.drop_constraint("ck_audit_findings_status", "audit_findings", type_="check")
    op.create_check_constraint(
        "ck_audit_findings_status", "audit_findings", f"status IN ({_STATUSES})"
    )
