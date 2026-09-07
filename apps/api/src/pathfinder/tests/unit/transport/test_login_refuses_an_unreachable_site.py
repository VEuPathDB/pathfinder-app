"""A sign-in against a site that does not answer is a refusal, not a 500.

``password_login`` posts with no error mapping, so a transport failure would
otherwise leave the route with an unhandled exception and the browser with an
opaque 500 after the client's whole read timeout.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import cast

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI, Request, Response

from pathfinder.platform.error_handlers import app_error_handler
from pathfinder.platform.errors import AppError
from pathfinder.platform.security import limiter
from pathfinder.transport.http.routers.veupathdb_auth import router

_CREDENTIALS = {"email": "researcher@example.org", "password": "secret"}


def _app(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> FastAPI:
    """An app whose VEuPathDB login raises *failure*."""

    async def _login(*args: object, **kwargs: object) -> str | None:
        del args, kwargs
        raise failure

    monkeypatch.setattr(
        "pathfinder.transport.http.routers.veupathdb_auth.start_veupathdb_session",
        _login,
    )

    async def _session() -> AsyncGenerator[None]:
        yield None

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.add_exception_handler(
        AppError,
        cast("Callable[[Request, Exception], Awaitable[Response]]", app_error_handler),
    )
    app.dependency_overrides[get_db_session] = _session
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.parametrize(
    "failure",
    [httpx.ReadTimeout("timed out"), httpx.ConnectError("refused")],
)
async def test_a_site_that_does_not_answer_is_a_503(
    failure: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(monkeypatch, failure)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/veupathdb/auth/login",
            params={"siteId": "veupathdb"},
            json=_CREDENTIALS,
        )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SITE_UNAVAILABLE"
    assert body["detail"] == (
        f"veupathdb is not responding ({type(failure).__name__})."
    )
