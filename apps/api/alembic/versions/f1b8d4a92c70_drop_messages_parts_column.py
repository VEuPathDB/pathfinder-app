"""drop_messages_parts_column

Revision ID: f1b8d4a92c70
Revises: e3a91d22f4c1
Create Date: 2026-04-28 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1b8d4a92c70"
down_revision: str | Sequence[str] | None = "e3a91d22f4c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sqlalchemy.text(
            """
            INSERT INTO conversation_events (
                conversation_id, turn_id, task_id, chunk
            )
            SELECT
                m.conversation_id,
                m.id AS turn_id,
                NULL AS task_id,
                jsonb_build_object(
                    'type',
                    CASE m.role
                        WHEN 'user' THEN 'user-message'
                        WHEN 'system' THEN 'system-message'
                        ELSE 'assistant-message'
                    END,
                    'message', jsonb_build_object(
                        'id', m.id::text,
                        'role', m.role,
                        'parts', m.parts
                    )
                ) AS chunk
            FROM messages m
            WHERE m.parts IS NOT NULL
              AND jsonb_array_length(m.parts) > 0
            """,
        ),
    )
    op.drop_column("messages", "parts")


def downgrade() -> None:
    op.add_column(
        "messages",
        sqlalchemy.Column(
            "parts",
            postgresql.JSONB(astext_type=sqlalchemy.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
