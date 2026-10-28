"""What this application pins about the ``veupathdb-mcp`` distribution it installs.

The server and the semantic index are a separate distribution with settings of
their own. This application extends both and installs itself as their source,
and it shares one database with them without sharing a declarative base.
"""

from __future__ import annotations

import pytest
from assistant_core.mcp.untrusted import stream_part_meta_key
from assistant_core.persistence.models import Base
from pydantic import ValidationError
from veupathdb_mcp import tool_meta
from veupathdb_mcp.embeddings import (
    EmbeddingBase,
    EmbeddingSettings,
    get_embedding_settings,
)
from veupathdb_mcp.settings import McpSettings, get_mcp_settings

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
    assert stream_part_meta_key() == tool_meta.STREAM_PART_META_KEY


def test_one_openai_key_serves_the_models_and_the_decisions() -> None:
    settings = Settings(openai_api_key="sk-test")

    assert settings.deployment_credential("openai") == "sk-test"


def test_the_application_needs_the_openai_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is not set"):
        Settings(openai_api_key="")
