"""The PathFinder session cookie carries one set of attributes wherever it is written."""

from __future__ import annotations

from collections.abc import Iterator
from http.cookies import SimpleCookie

import pytest
from fastapi import Response

from pathfinder.platform.config import get_settings
from pathfinder.platform.security import clear_session_cookie, set_session_cookie

_SCOPE = {"httponly": True, "path": "/pathfinder", "samesite": "lax"}


@pytest.fixture
def _development(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("API_ENV", "development")
    monkeypatch.setenv("PATHFINDER_CHAT_PROVIDER", "default")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-unit-test-only")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _written(response: Response) -> tuple[str, str, dict[str, object]]:
    """The one cookie the response writes: its name, value and set attributes."""
    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 1
    jar = SimpleCookie()
    jar.load(headers[0])
    ((name, morsel),) = jar.items()
    attributes = {
        key: value
        for key, value in morsel.items()
        if value and key not in {"expires", "max-age"}
    }
    return name, morsel.value, attributes


def test_a_set_session_is_secure_outside_development() -> None:
    response = Response()

    set_session_cookie(response, "session-token")

    assert _written(response) == (
        "pathfinder-auth",
        "session-token",
        {**_SCOPE, "secure": True},
    )


@pytest.mark.usefixtures("_development")
def test_a_set_session_is_not_secure_in_development() -> None:
    response = Response()

    set_session_cookie(response, "session-token")

    assert _written(response) == ("pathfinder-auth", "session-token", _SCOPE)


def test_a_cleared_session_expires_under_the_same_scope() -> None:
    response = Response()

    clear_session_cookie(response)

    assert _written(response) == ("pathfinder-auth", "", {**_SCOPE, "secure": True})
    assert "Max-Age=0" in response.headers["set-cookie"].split("; ")


@pytest.mark.usefixtures("_development")
def test_a_cleared_session_is_not_secure_in_development() -> None:
    response = Response()

    clear_session_cookie(response)

    assert _written(response) == ("pathfinder-auth", "", _SCOPE)
