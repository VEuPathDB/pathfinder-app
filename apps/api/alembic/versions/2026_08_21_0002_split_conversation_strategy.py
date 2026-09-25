"""split_conversation_strategy

Revision ID: 2026_08_21_0002
Revises: 2026_08_21_0001
Create Date: 2026-08-21 00:00:00.000000

A conversation gets a side row only when it holds strategy state. A JSON
``null`` AST means the strategy was cleared, so it moves as an empty object.
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "2026_08_21_0002"
down_revision: str | Sequence[str] | None = "2026_08_21_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MOVED_COLUMNS: tuple[str, ...] = (
    "record_type",
    "wdk_strategy_id",
    "is_saved",
    "step_count",
    "strategy_ast",
    "estimated_size",
    "gene_set_id",
    "gene_set_auto_imported",
    "experiment_id",
    "imported_saved_strategy_ids",
)

_NORMALIZED_AST = (
    "CASE WHEN strategy_ast IS NULL OR strategy_ast::jsonb = 'null'::jsonb "
    "THEN '{}'::jsonb ELSE strategy_ast::jsonb END"
)

_HOLDS_STRATEGY = """
    record_type IS NOT NULL
    OR wdk_strategy_id IS NOT NULL
    OR is_saved
    OR step_count <> 0
    OR (
        strategy_ast IS NOT NULL
        AND strategy_ast::jsonb <> '{}'::jsonb
        AND strategy_ast::jsonb <> 'null'::jsonb
    )
    OR estimated_size IS NOT NULL
    OR gene_set_id IS NOT NULL
    OR gene_set_auto_imported
    OR (
        imported_saved_strategy_ids IS NOT NULL
        AND imported_saved_strategy_ids::jsonb <> '[]'::jsonb
    )
    OR experiment_id IS NOT NULL
"""


def _conversations() -> sqlalchemy.TableClause:
    return sqlalchemy.table(
        "conversations",
        sqlalchemy.column("id"),
        *(sqlalchemy.column(name) for name in _MOVED_COLUMNS),
    )


def _strategies() -> sqlalchemy.TableClause:
    return sqlalchemy.table(
        "conversation_strategies",
        sqlalchemy.column("conversation_id"),
        *(sqlalchemy.column(name) for name in _MOVED_COLUMNS),
    )


def upgrade() -> None:
    op.create_table(
        "conversation_strategies",
        sqlalchemy.Column(
            "conversation_id",
            sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
            sqlalchemy.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sqlalchemy.Column("record_type", sqlalchemy.String(100), nullable=True),
        sqlalchemy.Column("wdk_strategy_id", sqlalchemy.Integer, nullable=True),
        sqlalchemy.Column(
            "is_saved",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
        sqlalchemy.Column(
            "step_count", sqlalchemy.Integer, nullable=False, server_default="0"
        ),
        sqlalchemy.Column("strategy_ast", JSONB, nullable=False, server_default="{}"),
        sqlalchemy.Column("estimated_size", sqlalchemy.Integer, nullable=True),
        sqlalchemy.Column(
            "gene_set_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("gene_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sqlalchemy.Column(
            "gene_set_auto_imported",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
        sqlalchemy.Column(
            "experiment_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("experiments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sqlalchemy.Column(
            "imported_saved_strategy_ids",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )
    # The application owns this value, so no row may take a database default.
    op.alter_column(
        "conversation_strategies",
        "imported_saved_strategy_ids",
        server_default=None,
    )
    op.create_index(
        "ix_conversation_strategies_wdk_strategy_id",
        "conversation_strategies",
        ["wdk_strategy_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("wdk_strategy_id IS NOT NULL"),
    )

    conversations = _conversations()
    moved = sqlalchemy.select(
        conversations.c.id,
        *(
            sqlalchemy.text(_NORMALIZED_AST)
            if name == "strategy_ast"
            else conversations.c[name]
            for name in _MOVED_COLUMNS
        ),
    ).where(sqlalchemy.text(_HOLDS_STRATEGY))
    op.execute(
        _strategies()
        .insert()
        .from_select(
            ["conversation_id", *_MOVED_COLUMNS],
            moved,
        ),
    )

    op.drop_index("ix_conversations_wdk_strategy_id", table_name="conversations")
    for column in _MOVED_COLUMNS:
        op.drop_column("conversations", column)


def downgrade() -> None:
    op.add_column(
        "conversations",
        sqlalchemy.Column("record_type", sqlalchemy.String(100), nullable=True),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column("wdk_strategy_id", sqlalchemy.Integer, nullable=True),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "is_saved",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "step_count", sqlalchemy.Integer, nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column("strategy_ast", JSONB, nullable=False, server_default="{}"),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column("estimated_size", sqlalchemy.Integer, nullable=True),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "gene_set_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("gene_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "gene_set_auto_imported",
            sqlalchemy.Boolean,
            nullable=False,
            server_default=sqlalchemy.text("false"),
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "experiment_id",
            sqlalchemy.String(50),
            sqlalchemy.ForeignKey("experiments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sqlalchemy.Column(
            "imported_saved_strategy_ids",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )

    conversations = _conversations()
    strategies = _strategies()
    op.execute(
        conversations.update()
        .values({name: strategies.c[name] for name in _MOVED_COLUMNS})
        .where(conversations.c.id == strategies.c.conversation_id),
    )
    # The application owns this value, so no row may take a database default.
    op.alter_column(
        "conversations",
        "imported_saved_strategy_ids",
        server_default=None,
    )

    op.create_index(
        "ix_conversations_wdk_strategy_id",
        "conversations",
        ["wdk_strategy_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("wdk_strategy_id IS NOT NULL"),
    )
    op.drop_table("conversation_strategies")
