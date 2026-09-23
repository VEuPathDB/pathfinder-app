"""The auth routes answer 503 naming the site when its identity read does not answer.

A refused token still reads as signed out, and a bad password still reads as
invalid credentials; only an outage is a 503.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI, Request, Response
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import WDKUserInfo

from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.platform.readiness import reset_readiness
from pathfinder.platform.security import create_user_token, limiter
from pathfinder.transport.http.routers import veupathdb_auth
from pathfinder.transport.http.routers.veupathdb_auth import router

_CREDENTIALS = {"email": "researcher@example.org", "password": "secret"}
_UNAVAILABLE = "Could not connect to plasmodb (the site did not answer in time)."


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_readiness()


def _outage() -> WDKError:
    """The error an identity read raises when the site misses its deadline."""
    error = WDKError("GET /users/current failed", status=502)
    error.__cause__ = TimeoutError()
    return error


def _app() -> FastAPI:
    async def _session() -> AsyncGenerator[None]:
        yield None

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.add_exception_handler(
        VEuPathDBError,
        cast(
            "Callable[[Request, Exception], Awaitable[Response]]",
            veupathdb_error_handler,
        ),
    )
    app.dependency_overrides[get_db_session] = _session
    return app


def _current_user(monkeypatch: pytest.MonkeyPatch, answer: WDKUserInfo | None) -> None:
    async def _fetch(site_id: str) -> WDKUserInfo | None:
        del site_id
        return answer

    monkeypatch.setattr(veupathdb_auth, "fetch_current_user", _fetch)


def _current_user_fails(monkeypatch: pytest.MonkeyPatch, outage: WDKError) -> None:
    async def _fetch(site_id: str) -> WDKUserInfo | None:
        del site_id
        raise outage

    monkeypatch.setattr(veupathdb_auth, "fetch_current_user", _fetch)


def _registered_email(monkeypatch: pytest.MonkeyPatch, outage: WDKError) -> None:
    async def _email(token: str, site_id: str) -> str | None:
        del token, site_id
        raise outage

    monkeypatch.setattr(veupathdb_auth, "resolve_registered_email", _email)


async def _call(app: FastAPI, method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(
            method,
            f"/api/v1/veupathdb/auth/{path}",
            params={"siteId": "plasmodb"},
            **kwargs,
        )


_REFUSAL = (503, "SITE_UNAVAILABLE", _UNAVAILABLE)


def _refusal(response: httpx.Response) -> tuple[int, str, str]:
    body = response.json()
    return (response.status_code, body["code"], body["detail"])


class TestStatus:
    async def test_an_outage_is_a_503_naming_the_site(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _current_user_fails(monkeypatch, _outage())

        assert _refusal(await _call(_app(), "GET", "status")) == _REFUSAL

    async def test_a_refused_token_is_signed_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _current_user(monkeypatch, None)

        response = await _call(_app(), "GET", "status")

        assert response.status_code == 200
        assert response.json() == {"signedIn": False, "name": None, "email": None}

    async def test_a_guest_is_signed_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _current_user(monkeypatch, WDKUserInfo(id=9, is_guest=True, email=None))

        response = await _call(_app(), "GET", "status")

        assert response.status_code == 200
        assert response.json()["signedIn"] is False


class TestLogin:
    async def test_an_outage_is_a_503_not_a_bad_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _login(*args: object, **kwargs: object) -> str:
            del args, kwargs
            return "veupathdb-jwt"

        monkeypatch.setattr(veupathdb_auth, "password_login", _login)
        _registered_email(monkeypatch, _outage())

        response = await _call(_app(), "POST", "login", json=_CREDENTIALS)

        assert _refusal(response) == _REFUSAL


class TestRefresh:
    async def test_an_outage_is_a_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _registered_email(monkeypatch, _outage())

        response = await _call(
            _app(),
            "POST",
            "refresh",
            cookies={"Authorization": "veupathdb-jwt"},
        )

        assert _refusal(response) == _REFUSAL

    async def test_an_outage_leaves_the_session_cookie_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _registered_email(monkeypatch, _outage())

        response = await _call(
            _app(),
            "POST",
            "refresh",
            cookies={
                "pathfinder-auth": create_user_token(
                    UUID("aa873910-0000-4000-8000-000000000001")
                ),
                "Authorization": "veupathdb-jwt",
            },
        )

        assert _refusal(response) == _REFUSAL
        assert "set-cookie" not in response.headers
