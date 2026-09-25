"""Name the call a durable task answers, and flush every checkpoint.

A durable tool now defers its pydantic-ai call instead of interrupting the
graph, so ``background_tasks`` records the call its result answers. This
flushes every checkpoint, because the state shape gained the parked durable
call and a strict state does not read an older shape - not only the threads
that were interrupted. A flushed thread loses its graph state, its pending
approvals, its turn totals and a one-agent thread's message history, and
resumes from a fresh turn; conversations, the durable event log, messages,
strategies and background tasks are untouched.

Revision ID: 2026_08_30_0001
Revises: 2026_08_29_0001
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_08_30_0001"
down_revision: str | Sequence[str] | None = "2026_08_29_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every row goes, not only an interrupted thread's: a strict state does not
# read a shape written before it gained the parked durable call. The
# checkpointer lifespan creates these tables, not alembic, so a database that
# has never run a turn has nothing to flush.
_FLUSH_CHECKPOINTS = """
DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'checkpoint_writes',
        'checkpoint_blobs',
        'checkpoints'
    ]
    LOOP
        IF to_regclass('public.' || tbl) IS NOT NULL THEN
            EXECUTE format('TRUNCATE TABLE %I', tbl);
        END IF;
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.add_column(
        "background_tasks",
        sqlalchemy.Column("tool_call_id", sqlalchemy.String(length=128), nullable=True),
    )
    op.execute(_FLUSH_CHECKPOINTS)


def downgrade() -> None:
    op.drop_column("background_tasks", "tool_call_id")
