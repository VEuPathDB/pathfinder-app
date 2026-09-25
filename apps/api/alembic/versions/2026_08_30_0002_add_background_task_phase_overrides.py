"""Carry the request's per-phase picks on the durable task row.

The turn that answers a durable call is opened by the worker, from the
conversation row and the checkpoint. Neither carries the request-scoped model
and reasoning picks, so the task row does.

Revision ID: 2026_08_30_0002
Revises: 2026_08_30_0001
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_08_30_0002"
down_revision: str | Sequence[str] | None = "2026_08_30_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "background_tasks",
        sqlalchemy.Column(
            "phase_overrides",
            postgresql.JSONB(astext_type=sqlalchemy.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("background_tasks", "phase_overrides")
