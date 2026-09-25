"""Lead+Ledger architecture migration.

Wipes LangGraph checkpoint state because ``PipelineState`` lost 9 fields
(current_phase, last_routing_reason, supervisor_call_count,
phase_call_counts, last_assistant_prose, last_phase_outcome,
last_verification_message_id, specialist_mode, supervisor_log) and gained
3 (user_intent, lead_next_state, last_build_outcome). Old serialized
states cannot deserialize against the new schema; cleanest fix is to
flush them and let conversations resume from a fresh turn.

Drops the orphaned per-user / per-conversation specialist columns:
``users.specialist_model_defaults`` and ``conversations.specialist_mode``
no longer have any code reading them.

Revision ID: 2026_05_07_0001
Revises: 2026_05_04_0001
Create Date: 2026-05-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_05_07_0001"
down_revision: str | Sequence[str] | None = "2026_05_04_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            tbl text;
        BEGIN
            FOREACH tbl IN ARRAY ARRAY[
                'checkpoint_writes',
                'checkpoint_blobs',
                'checkpoints',
                'checkpoint_labels'
            ]
            LOOP
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = tbl
                ) THEN
                    EXECUTE format('TRUNCATE TABLE %I RESTART IDENTITY', tbl);
                END IF;
            END LOOP;
        END $$;
        """
    )
    op.drop_column("conversations", "specialist_mode")
    op.drop_column("conversations", "supervisor_model_id")
    op.drop_column("conversations", "pipeline")
    op.drop_column("users", "specialist_model_defaults")
    op.drop_column("users", "supervisor_model_id")
    op.drop_column("users", "pipeline_config")


def downgrade() -> None:
    op.add_column(
        "users",
        sqlalchemy.Column(
            "specialist_model_defaults",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "users",
        sqlalchemy.Column(
            "supervisor_model_id",
            sqlalchemy.String(length=128),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sqlalchemy.Column(
            "pipeline_config",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "specialist_mode",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "supervisor_model_id",
            sqlalchemy.String(length=128),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "pipeline",
            sqlalchemy.JSON(),
            nullable=True,
        ),
    )
