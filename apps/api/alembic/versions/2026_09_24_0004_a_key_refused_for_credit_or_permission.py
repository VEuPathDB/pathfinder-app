"""A stored key may be marked refused for its credit or its permissions.

The downgrade marks such a key ``invalid``, so it stays refused under the
older constraint.

Revision ID: 2026_09_24_0004
Revises: 2026_09_24_0003
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_09_24_0004"
down_revision: str | Sequence[str] | None = "2026_09_24_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_provider_keys"
_CHECK = "ck_user_provider_keys_refusal"


def upgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK,
        _TABLE,
        "refusal IS NULL OR refusal IN "
        "('invalid', 'no_credit', 'forbidden', 'unreadable')",
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.execute(
        sqlalchemy.text(
            "UPDATE user_provider_keys SET refusal = 'invalid' "
            "WHERE refusal IN ('no_credit', 'forbidden')"
        )
    )
    op.create_check_constraint(
        _CHECK, _TABLE, "refusal IS NULL OR refusal IN ('invalid', 'unreadable')"
    )
