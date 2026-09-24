"""The seam between a chat thread and PathFinder's strategy projection.

``conversations`` is what a second assistant reuses, so a WDK column that
lands back on it is a regression even when every other test still passes.
"""

from __future__ import annotations

from assistant_core.persistence.models import Conversation
from sqlalchemy import Index, Table
from sqlalchemy.ext.asyncio import create_async_engine

from pathfinder.persistence.models import (
    ConversationStrategy,
    ConversationStrategyView,
    StrategyRevision,
)

THREAD_COLUMNS = {
    "id",
    "user_id",
    "application_id",
    "assistant_id",
    "site_id",
    "name",
    "dismissed_at",
    "parent_conversation_id",
    "parent_message_id",
    "created_at",
    "updated_at",
}

STRATEGY_COLUMNS = {
    "record_type",
    "wdk_strategy_id",
    "wdk_strategy_created_here",
    "is_saved",
    "step_count",
    "strategy_ast",
    "estimated_size",
    "gene_set_id",
    "gene_set_auto_imported",
    "imported_saved_strategy_ids",
}


_THREADS: Table = Conversation.metadata.tables["conversations"]
_SIDE_TABLE: Table = ConversationStrategy.metadata.tables["conversation_strategies"]
_REVISIONS: Table = StrategyRevision.metadata.tables["strategy_revisions"]


def _column_names(model: type[Conversation] | type[ConversationStrategy]) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_the_thread_carries_only_the_thread_columns() -> None:
    assert _column_names(Conversation) == THREAD_COLUMNS


def test_the_thread_carries_no_strategy_column() -> None:
    assert _column_names(Conversation) & STRATEGY_COLUMNS == set()


def test_the_side_table_carries_the_strategy_columns_keyed_by_conversation() -> None:
    assert _column_names(ConversationStrategy) == STRATEGY_COLUMNS | {"conversation_id"}


def test_the_side_table_has_no_application_of_its_own() -> None:
    """Scoping comes from the parent, so the child cannot name another owner."""
    assert "application_id" not in _column_names(ConversationStrategy)
    assert "user_id" not in _column_names(ConversationStrategy)


def test_the_side_row_is_the_primary_key_and_cascades_from_its_parent() -> None:
    table = _SIDE_TABLE
    assert [column.name for column in table.primary_key.columns] == ["conversation_id"]
    parent = next(
        fk
        for fk in table.foreign_keys
        if fk.column.table.name == "conversations"
        and fk.parent.name == "conversation_id"
    )
    assert parent.ondelete == "CASCADE"


def test_the_unique_wdk_strategy_index_moved_to_the_side_table() -> None:
    conversation_indexes = {index.name for index in _THREADS.indexes}
    assert "ix_conversations_wdk_strategy_id" not in conversation_indexes

    index: Index = next(
        index
        for index in _SIDE_TABLE.indexes
        if index.name == "ix_conversation_strategies_wdk_strategy_id"
    )
    assert index.unique
    assert index.dialect_options["postgresql"]["where"] == (
        "wdk_strategy_id IS NOT NULL"
    )


def test_the_strategy_ast_column_maps_the_jsonb_the_chain_built() -> None:
    """Both columns that hold a strategy AST compile to the type the chain built."""
    dialect = create_async_engine("postgresql+asyncpg://pathfinder@db/pf").dialect
    column = _SIDE_TABLE.c.strategy_ast

    assert column.type.compile(dialect) == "JSONB"
    assert column.nullable is False
    assert _REVISIONS.c.strategy_ast.type.compile(dialect) == "JSONB"


def test_the_thread_declares_no_relationship_to_the_science() -> None:
    """The thread is the runtime's; a caller that wants the strategy asks for it."""
    assert dict(Conversation.__mapper__.relationships) == {}


def test_an_absent_row_reads_as_a_strategy_that_was_never_built() -> None:
    view = ConversationStrategyView()

    assert view.record_type is None
    assert view.wdk_strategy_id is None
    assert view.wdk_strategy_created_here is False
    assert view.is_saved is False
    assert view.step_count == 0
    assert view.strategy_ast == {}
    assert view.estimated_size is None
    assert view.gene_set_id is None
    assert view.gene_set_auto_imported is False
    assert view.imported_saved_strategy_ids == []


def test_the_view_projects_every_column_of_the_side_row() -> None:
    assert set(ConversationStrategyView.model_fields) == STRATEGY_COLUMNS
