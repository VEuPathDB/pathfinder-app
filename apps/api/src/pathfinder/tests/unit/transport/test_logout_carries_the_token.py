"""Logging out sends the user's token, because WDK logs out whoever asked.

A request with no credential is answered as a guest, and WDK returns early for
a guest without touching anyone's session. The user is then told they are
logged out while their token still works.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from pathfinder.platform.security import limiter
from pathfinder.transport.http.routers import veupathdb_auth

_TOKEN = "eyJhbGciOiJFUzUxMiJ9.real-user.sig"


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record every logout the route asks WDK for."""
    calls: list[tuple[str, str]] = []

    async def _logout(site_id: str, auth_token: str) -> bool:
        calls.append((site_id, auth_token))
        return True

    monkeypatch.setattr(veupathdb_auth, "password_logout", _logout)
    return calls


def _app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(veupathdb_auth.router)
    return app


async def _logout(cookies: dict[str, str]) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies=cookies
    ) as client:
        return await client.post(
            "/api/v1/veupathdb/auth/logout", params={"siteId": "plasmodb"}
        )


class TestTheRouteCarriesTheCredential:
    async def test_the_token_reaches_wdk(self, seen: list[tuple[str, str]]) -> None:
        response = await _logout({"Authorization": _TOKEN})

        assert seen == [("plasmodb", _TOKEN)]
        assert response.json() == {"success": True}

    async def test_without_a_token_wdk_is_not_asked(
        self, seen: list[tuple[str, str]]
    ) -> None:
        response = await _logout({})

        assert seen == []
        assert response.json() == {"success": False}


class TestTheCookiesGoEitherWay:
    async def test_a_refused_logout_still_clears_the_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _refused(site_id: str, auth_token: str) -> bool:
            del site_id, auth_token
            return False

        monkeypatch.setattr(veupathdb_auth, "password_logout", _refused)

        response = await _logout({"Authorization": _TOKEN})

        assert response.json() == {"success": False}
        cleared = response.headers.get_list("set-cookie")
        assert any(entry.startswith("Authorization=") for entry in cleared)
        assert any(entry.startswith("pathfinder-auth=") for entry in cleared)
