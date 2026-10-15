"""A browser request is signed in by the hosting website's login alone; PathFinder
keeps no session of its own beside it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, cast
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Request, Response
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.platform.principal import Principal
from pathfinder.platform.security import (
    DEV_LOGIN_COOKIE,
    create_dev_login_token,
    create_user_token,
    resolve_principal,
    site_login_user,
)


def _app(site_user: UUID | None) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(
        VEuPathDBError,
        cast(
            "Callable[[Request, Exception], Awaitable[Response]]",
            veupathdb_error_handler,
        ),
    )

    @app.get("/who")
    async def who(
        principal: Annotated[Principal, Depends(resolve_principal)],
    ) -> dict[str, str]:
        return {"user": str(principal.user_id), "credential": principal.credential}

    async def _site_user() -> UUID | None:
        return site_user

    app.dependency_overrides[site_login_user] = _site_user
    return app


async def _get(app: FastAPI, cookies: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies=cookies
    ) as client:
        return await client.get("/who")


async def test_the_site_login_alone_names_the_user() -> None:
    user = uuid4()

    response = await _get(_app(user))

    assert response.status_code == 200
    assert response.json() == {"user": str(user), "credential": "veupathdb-cookie"}


async def test_no_site_login_is_not_authenticated() -> None:
    response = await _get(_app(None))

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


async def test_a_pathfinder_session_cookie_signs_nobody_in() -> None:
    response = await _get(_app(None), {"pathfinder-auth": create_user_token(uuid4())})

    assert response.status_code == 401


async def test_a_dev_login_cookie_names_its_synthetic_user() -> None:
    user = uuid4()

    response = await _get(_app(None), {DEV_LOGIN_COOKIE: create_dev_login_token(user)})

    assert response.json() == {"user": str(user), "credential": "dev-login"}


async def test_a_user_token_in_the_dev_login_cookie_signs_nobody_in() -> None:
    response = await _get(_app(None), {DEV_LOGIN_COOKIE: create_user_token(uuid4())})

    assert response.status_code == 401
