"""A deployment that seals researchers' provider keys under a test secret."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from pathfinder.platform.config import get_settings

_ENV = "PROVIDER_KEY_ENCRYPTION_KEY"


def made_up_secret(fill: int = 7) -> str:
    """The base64url of 32 bytes, as an operator writes the setting."""
    return base64.urlsafe_b64encode(bytes([fill]) * 32).decode()


@contextmanager
def sealed_provider_keys(
    monkeypatch: pytest.MonkeyPatch, secret: str | None = None
) -> Iterator[None]:
    """Every settings read in the scope, the app's included, holds the secret."""
    monkeypatch.setenv(_ENV, secret or made_up_secret())
    get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.delenv(_ENV)
        get_settings.cache_clear()
