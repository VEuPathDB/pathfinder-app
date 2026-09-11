"""What this application pins about the ``veupathdb-mcp`` distribution it installs.

The server and the semantic index are a separate distribution with settings of
their own. This application extends both and installs itself as their source,
and it shares one database with them without sharing a declarative base.
"""

from __future__ import annotations

from assistant_core.mcp.untrusted import STREAM_PART_META_KEY
from assistant_core.persistence.models import Base
from veupathdb_mcp import McpSettings, get_mcp_settings, tool_meta
from veupathdb_mcp.embeddings import (
    EmbeddingBase,
    EmbeddingSettings,
    get_embedding_settings,
)

from pathfinder.platform.config import Settings, get_settings


def test_the_host_instance_serves_the_server() -> None:
    assert get_mcp_settings() is get_settings()


def test_the_host_instance_serves_the_index() -> None:
    assert get_embedding_settings() is get_settings()


def test_the_application_settings_extend_both() -> None:
    assert issubclass(Settings, McpSettings)
    assert issubclass(Settings, EmbeddingSettings)


def test_the_runtime_base_maps_neither_index_table() -> None:
    assert set(EmbeddingBase.metadata.tables) & set(Base.metadata.tables) == set()


def test_the_stream_part_key_is_the_vocabulary_the_runtime_reads() -> None:
    """Two distributions state the same wire key; neither imports the other."""
    assert tool_meta.STREAM_PART_META_KEY == STREAM_PART_META_KEY
