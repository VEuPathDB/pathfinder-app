"""Add the researchers' provider keys, sealed under the server secret.

One live row per user, application and provider. A revoked row keeps its hint
and drops its ciphertext.

Revision ID: 2026_09_24_0002
Revises: 2026_09_24_0001
"""

from collections.abc import Sequence

import sqlalchemy
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
        sqlalchemy.Column("id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column("user_id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column(
            "application_id",
            sqlalchemy.String(length=64),
            nullable=False,
            server_default="default",
        ),
        sqlalchemy.Column("provider", sqlalchemy.String(length=16), nullable=False),
        sqlalchemy.Column("ciphertext", sqlalchemy.LargeBinary(), nullable=True),
        sqlalchemy.Column("hint", sqlalchemy.String(length=4), nullable=False),
        sqlalchemy.Column(
            "created_at",
            sqlalchemy.DateTime(timezone=True),
            nullable=False,
            server_default=sqlalchemy.text("now()"),
        ),
        sqlalchemy.Column(
            "revoked_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.Column(
            "refused_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.Column("refusal", sqlalchemy.String(length=16), nullable=True),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sqlalchemy.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'google')",
            name="ck_user_provider_keys_provider",
        ),
        sqlalchemy.CheckConstraint(
            "(revoked_at IS NULL) = (ciphertext IS NOT NULL)",
            name="ck_user_provider_keys_live_holds_the_key",
        ),
        sqlalchemy.CheckConstraint(
            "(refused_at IS NULL) = (refusal IS NULL)",
            name="ck_user_provider_keys_refusal_has_a_time",
        ),
        sqlalchemy.CheckConstraint(
            "refusal IS NULL OR refusal IN ('invalid', 'unreadable')",
            name="ck_user_provider_keys_refusal",
        ),
    )
    op.create_index(
        _LIVE,
        _TABLE,
        ["user_id", "application_id", "provider"],
        unique=True,
        postgresql_where=sqlalchemy.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_LIVE, table_name=_TABLE)
    op.drop_table(_TABLE)
