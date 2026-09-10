"""The Langfuse client singleton: built once, and None when unconfigured."""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from pathfinder.platform.langfuse import client
from pathfinder.platform.langfuse.client import get_langfuse


@pytest.fixture(autouse=True)
def _fresh_singleton() -> Iterator[None]:
    client._state.client = None
    client._state.initialized = False
    yield
    client._state.client = None
    client._state.initialized = False


def test_get_langfuse_returns_none_when_not_configured() -> None:
    """An empty secret key builds no client and records the attempt."""
    mock_settings = MagicMock(
        langfuse_secret_key="", langfuse_public_key="", langfuse_host=""
    )
    with patch.object(client, "get_settings", return_value=mock_settings):
        result = get_langfuse()

    assert result is None
    assert client._state.initialized is True
    assert client._state.client is None


def test_get_langfuse_returns_cached_none() -> None:
    """A second call reads the singleton and never looks at the settings."""
    client._state.initialized = True

    with patch.object(client, "get_settings", side_effect=AssertionError) as settings:
        result = get_langfuse()

    assert result is None
    assert settings.call_count == 0
