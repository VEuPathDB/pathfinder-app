"""Add the researchers' provider keys, sealed under the server secret.

One live row per user, application and provider. A revoked row keeps its hint
and drops its ciphertext.

Revision ID: 2026_09_24_0002
Revises: 2026_09_24_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026_09_24_0002"
down_revision: str | Sequence[str] | None = "2026_09_24_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_provider_keys"
_LIVE = "uq_user_provider_keys_live"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.CHAR(length=36), nullable=False),
        sa.Column(
            "application_id",
            sa.String(length=64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("hint", sa.String(length=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refusal", sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'google')",
            name="ck_user_provider_keys_provider",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (ciphertext IS NOT NULL)",
            name="ck_user_provider_keys_live_holds_the_key",
        ),
        sa.CheckConstraint(
            "(refused_at IS NULL) = (refusal IS NULL)",
            name="ck_user_provider_keys_refusal_has_a_time",
        ),
        sa.CheckConstraint(
            "refusal IS NULL OR refusal IN ('invalid', 'unreadable')",
            name="ck_user_provider_keys_refusal",
        ),
    )
    op.create_index(
        _LIVE,
        _TABLE,
        ["user_id", "application_id", "provider"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_LIVE, table_name=_TABLE)
    op.drop_table(_TABLE)
