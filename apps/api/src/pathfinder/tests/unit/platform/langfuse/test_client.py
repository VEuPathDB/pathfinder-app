"""Tests for Langfuse SDK client singleton."""

from unittest.mock import MagicMock, patch

from pathfinder.platform.langfuse import client
from pathfinder.platform.langfuse.client import get_langfuse


def test_get_langfuse_returns_none_when_not_configured() -> None:
    """Returns None when LANGFUSE_SECRET_KEY is empty."""
    client._client = None
    client._initialized = False

    mock_settings = MagicMock(
        langfuse_secret_key="", langfuse_public_key="", langfuse_host=""
    )
    with patch.object(client, "get_settings", return_value=mock_settings):
        result = get_langfuse()

    assert result is None
    assert client._initialized is True

    # Reset
    client._client = None
    client._initialized = False


def test_get_langfuse_returns_cached_none() -> None:
    """Second call returns cached None without re-checking settings."""
    client._client = None
    client._initialized = True

    result = get_langfuse()
    assert result is None

    # Reset
    client._initialized = False
