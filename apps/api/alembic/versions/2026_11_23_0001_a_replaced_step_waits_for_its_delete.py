from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_11_23_0001"
down_revision: str | Sequence[str] | None = "2026_11_14_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_strategies",
        sqlalchemy.Column(
            "replaced_wdk_step_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::jsonb"),
        ),
    )
    op.alter_column(
        "conversation_strategies", "replaced_wdk_step_ids", server_default=None
    )


def downgrade() -> None:
    op.drop_column("conversation_strategies", "replaced_wdk_step_ids")
