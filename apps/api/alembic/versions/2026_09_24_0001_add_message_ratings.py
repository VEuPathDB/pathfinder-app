"""Add the message ratings, and let a disliked message stage its own eval case.

A rating row is one researcher's word on one assistant message, and it lists
the case keys that message wrote. A staged eval case may name the message it
came from, so one thread can stage one case per disliked message beside the
one extraction stages for the whole thread.

Revision ID: 2026_09_24_0001
Revises: 2026_09_16_0003
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026_09_24_0001"
down_revision: str | Sequence[str] | None = "2026_09_16_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAGED = "eval_staged_cases"
_LINKAGE = "ck_eval_staged_cases_linkage_ends_at_promotion"
_THREAD_INDEX = "ix_eval_staged_cases_source_conversation"
_MESSAGE_INDEX = "ix_eval_staged_cases_rated_message"

_LINKAGE_BEFORE = (
    "(status = 'staged'"
    " AND user_id IS NOT NULL"
    " AND source_conversation_id IS NOT NULL"
    " AND extract IS NOT NULL)"
    " OR "
    "(status = 'promoted'"
    " AND user_id IS NULL"
    " AND source_conversation_id IS NULL"
    " AND extract IS NULL)"
)
_LINKAGE_AFTER = (
    "(status = 'staged'"
    " AND user_id IS NOT NULL"
    " AND source_conversation_id IS NOT NULL"
    " AND extract IS NOT NULL)"
    " OR "
    "(status = 'promoted'"
    " AND user_id IS NULL"
    " AND source_conversation_id IS NULL"
    " AND extract IS NULL"
    " AND rated_message_id IS NULL)"
)


def upgrade() -> None:
    op.create_table(
        "message_ratings",
        sqlalchemy.Column(
            "id", sqlalchemy.BigInteger(), sqlalchemy.Identity(), nullable=False
        ),
        sqlalchemy.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sqlalchemy.Column(
            "conversation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sqlalchemy.Column("user_id", sqlalchemy.CHAR(length=36), nullable=False),
        sqlalchemy.Column("rating", sqlalchemy.String(length=8), nullable=True),
        sqlalchemy.Column(
            "case_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::jsonb"),
        ),
        sqlalchemy.Column(
            "withheld_cases",
            postgresql.JSONB(),
            nullable=False,
            server_default=sqlalchemy.text("'[]'::jsonb"),
        ),
        sqlalchemy.Column(
            "rated_at", sqlalchemy.DateTime(timezone=True), nullable=True
        ),
        sqlalchemy.Column(
            "updated_at",
            sqlalchemy.DateTime(timezone=True),
            nullable=False,
            server_default=sqlalchemy.text("now()"),
        ),
        sqlalchemy.PrimaryKeyConstraint("id"),
        sqlalchemy.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="CASCADE"
        ),
        sqlalchemy.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sqlalchemy.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sqlalchemy.UniqueConstraint(
            "message_id", "user_id", name="uq_message_ratings_message_user"
        ),
        sqlalchemy.CheckConstraint(
            "rating IS NULL OR rating IN ('like', 'dislike')",
            name="ck_message_ratings_rating",
        ),
    )
    op.create_index(
        "ix_message_ratings_user_rated", "message_ratings", ["user_id", "rating"]
    )
    op.create_index(
        "ix_message_ratings_conversation", "message_ratings", ["conversation_id"]
    )

    op.add_column(
        _STAGED,
        sqlalchemy.Column(
            "rated_message_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.drop_index(_THREAD_INDEX, table_name=_STAGED)
    op.create_index(
        _THREAD_INDEX,
        _STAGED,
        ["source_conversation_id"],
        unique=True,
        postgresql_where=sqlalchemy.text(
            "rated_message_id IS NULL AND source_conversation_id IS NOT NULL"
        ),
    )
    op.create_index(
        _MESSAGE_INDEX,
        _STAGED,
        ["rated_message_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("rated_message_id IS NOT NULL"),
    )
    op.drop_constraint(_LINKAGE, _STAGED, type_="check")
    op.create_check_constraint(_LINKAGE, _STAGED, _LINKAGE_AFTER)


def downgrade() -> None:
    # A thread held one staged row before, so the rated rows cannot stay.
    op.execute(
        sqlalchemy.text(
            "DELETE FROM eval_staged_cases WHERE rated_message_id IS NOT NULL"
        )
    )
    op.drop_constraint(_LINKAGE, _STAGED, type_="check")
    op.create_check_constraint(_LINKAGE, _STAGED, _LINKAGE_BEFORE)
    op.drop_index(_MESSAGE_INDEX, table_name=_STAGED)
    op.drop_index(_THREAD_INDEX, table_name=_STAGED)
    op.create_index(
        _THREAD_INDEX,
        _STAGED,
        ["source_conversation_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("source_conversation_id IS NOT NULL"),
    )
    op.drop_column(_STAGED, "rated_message_id")

    op.drop_index("ix_message_ratings_conversation", table_name="message_ratings")
    op.drop_index("ix_message_ratings_user_rated", table_name="message_ratings")
    op.drop_table("message_ratings")
