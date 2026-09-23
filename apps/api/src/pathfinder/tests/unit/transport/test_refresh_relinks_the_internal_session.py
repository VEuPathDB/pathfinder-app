"""The refresh route names the internal user of the live VEuPathDB session."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI, Request, Response
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.platform.security import (
    SessionToken,
    create_dev_login_token,
    create_user_token,
    decode_session_token,
)
from pathfinder.transport.http.routers.veupathdb_auth import router

TOKEN_ACCOUNT = uuid4()


def _app(monkeypatch: pytest.MonkeyPatch, resolved: UUID | None) -> FastAPI:
    """An app whose VEuPathDB lookup names ``resolved``, or nobody."""

    async def _link(*args: object, **kwargs: object) -> UUID | None:
        del args, kwargs
        return resolved

    monkeypatch.setattr(
        "pathfinder.transport.http.routers.veupathdb_auth._link_internal_user",
        _link,
    )

    async def _session() -> AsyncGenerator[None]:
        yield None

    app = FastAPI()
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


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _refreshed_session(response: httpx.Response) -> SessionToken:
    """The identity the refreshed ``pathfinder-auth`` cookie carries.

    The token's expiry follows the second it was signed in, so the claims are
    what a caller can compare and the encoded string is not.
    """
    cookie = response.cookies.get("pathfinder-auth")
    assert cookie is not None
    claims = decode_session_token(cookie)
    assert claims is not None
    return claims


@pytest.mark.asyncio
async def test_a_session_that_already_names_the_account_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, resolved=TOKEN_ACCOUNT)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/refresh",
            cookies={
                "pathfinder-auth": create_user_token(TOKEN_ACCOUNT),
                "Authorization": "veupathdb-jwt",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_a_session_naming_another_account_is_relinked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second VEuPathDB sign-in moves the session to the account it named."""
    app = _app(monkeypatch, resolved=TOKEN_ACCOUNT)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/refresh",
            cookies={
                "pathfinder-auth": create_user_token(uuid4()),
                "Authorization": "veupathdb-jwt",
            },
        )
    assert response.status_code == 200
    assert _refreshed_session(response) == SessionToken(sub=TOKEN_ACCOUNT)


@pytest.mark.asyncio
async def test_without_an_internal_session_the_token_is_minted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, resolved=TOKEN_ACCOUNT)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/refresh",
            cookies={"Authorization": "veupathdb-jwt"},
        )
    assert response.status_code == 200
    assert _refreshed_session(response) == SessionToken(sub=TOKEN_ACCOUNT)


@pytest.mark.asyncio
async def test_an_expired_internal_session_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, resolved=TOKEN_ACCOUNT)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/refresh",
            cookies={
                "pathfinder-auth": "not-a-valid-jwt",
                "Authorization": "veupathdb-jwt",
            },
        )
    assert response.status_code == 200
    assert _refreshed_session(response) == SessionToken(sub=TOKEN_ACCOUNT)


@pytest.mark.asyncio
async def test_an_unreadable_veupathdb_session_keeps_the_internal_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A VEuPathDB token the site refuses leaves the internal session in place."""
    app = _app(monkeypatch, resolved=None)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/refresh",
            cookies={
                "pathfinder-auth": create_user_token(TOKEN_ACCOUNT),
                "Authorization": "veupathdb-jwt",
            },
        )
    assert response.status_code == 200
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_no_session_at_all_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, resolved=None)
    async with _client(app) as client:
        response = await client.post("/api/v1/veupathdb/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_dev_login_session_is_never_relinked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dev-login session names no VEuPathDB account, so no token can move it."""
    app = _app(monkeypatch, resolved=TOKEN_ACCOUNT)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/refresh",
            cookies={
                "pathfinder-auth": create_dev_login_token(uuid4()),
                "Authorization": "veupathdb-jwt",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert "set-cookie" not in response.headers
