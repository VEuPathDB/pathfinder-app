"""The autogenerate filter that keeps another distribution's tables out of this chain."""

from __future__ import annotations

import pytest
from assistant_core.migrate import OWNED_TABLES, VERSION_TABLE
from veupathdb_mcp.embeddings.tables import EmbeddingBase

from pathfinder.platform.migrations import (
    LANGGRAPH_TABLES,
    MCP_VERSION_TABLE,
    PROCRASTINATE_PREFIX,
    include_object,
)


def _verdict(name: str, type_: str = "table", *, reflected: bool = False) -> bool:
    return include_object(None, name, type_, reflected, None)


@pytest.mark.parametrize("name", OWNED_TABLES)
def test_the_filter_drops_a_table_the_runtime_distribution_owns(name: str) -> None:
    """A table the runtime's chain builds never enters an application revision."""
    assert _verdict(name) is False


def test_the_filter_drops_the_version_table_the_runtime_chain_writes() -> None:
    """The runtime stamps `alembic_version_assistant_core`, so this chain leaves it."""
    assert VERSION_TABLE == "alembic_version_assistant_core"
    assert _verdict(VERSION_TABLE, reflected=True) is False


@pytest.mark.parametrize("name", sorted(EmbeddingBase.metadata.tables))
def test_the_filter_drops_a_table_the_tool_server_owns(name: str) -> None:
    """The semantic index is the tool server's chain, not this one's."""
    assert _verdict(name, reflected=True) is False


def test_the_filter_drops_the_version_table_the_tool_server_chain_writes() -> None:
    """The tool server stamps a version table of its own."""
    assert MCP_VERSION_TABLE == "alembic_version_veupathdb_mcp"
    assert _verdict(MCP_VERSION_TABLE, reflected=True) is False


@pytest.mark.parametrize(
    "name",
    ["procrastinate_jobs", "procrastinate_events", "procrastinate_workers"],
)
def test_the_filter_drops_a_queue_table(name: str) -> None:
    """The queue schema comes from a SQL file, so no model here maps it."""
    assert name.startswith(PROCRASTINATE_PREFIX)
    assert _verdict(name, reflected=True) is False


@pytest.mark.parametrize("name", sorted(LANGGRAPH_TABLES))
def test_the_filter_drops_a_checkpointer_or_store_table(name: str) -> None:
    """The checkpointer and the memory store build their tables when they open."""
    assert _verdict(name, reflected=True) is False


def test_the_filter_keeps_a_table_the_application_owns() -> None:
    """`users` is the application's, so autogenerate still compares it."""
    assert _verdict("users") is True


def test_the_filter_leaves_a_column_to_the_verdict_on_its_table() -> None:
    """Alembic gates a column on its table, so the filter passes columns through."""
    assert _verdict("user_id", type_="column", reflected=True) is True


def test_the_owned_names_are_the_ten_the_runtime_builds() -> None:
    """The filter reads the runtime's list, so the ten names are not retyped."""
    assert OWNED_TABLES == (
        "conversations",
        "messages",
        "conversation_events",
        "memory_tombstones",
        "chat_turn_cancellations",
        "monthly_usage",
        "scratchpad_notes",
        "scratchpad_compactions",
        "background_tasks",
        "task_progress",
    )


def test_the_checkpointer_and_store_names_are_the_eight_langgraph_opens() -> None:
    """A name that leaves this set comes back as a `remove_table` in a revision."""
    assert set(LANGGRAPH_TABLES) == {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        "store",
        "store_vectors",
        "store_migrations",
        "vector_migrations",
    }
