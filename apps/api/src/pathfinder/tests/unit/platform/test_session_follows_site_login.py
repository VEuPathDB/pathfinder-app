from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI, Request, Response
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.platform.principal import Principal
from pathfinder.platform.security import (
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
        return {"user": str(principal.user_id)}

    async def _site_user() -> UUID | None:
        return site_user

    app.dependency_overrides[site_login_user] = _site_user
    return app


async def _get(app: FastAPI, cookie: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("pathfinder-auth", cookie)
        return await client.get("/who")


async def test_a_session_whose_site_login_names_its_user_is_served() -> None:
    user = uuid4()

    response = await _get(_app(user), create_user_token(user))

    assert response.status_code == 200
    assert response.json() == {"user": str(user)}


async def test_a_session_with_no_site_login_is_signed_out() -> None:
    response = await _get(_app(None), create_user_token(uuid4()))

    assert response.status_code == 401
    assert response.json()["code"] == "WDK_LOGIN_REQUIRED"


async def test_a_session_whose_site_login_names_another_user_is_refused() -> None:
    response = await _get(_app(uuid4()), create_user_token(uuid4()))

    assert response.status_code == 401
    assert response.json()["code"] == "WDK_IDENTITY_MISMATCH"


@pytest.mark.parametrize("site_user", [None, uuid4()])
async def test_a_dev_login_session_does_not_follow_a_site_login(
    site_user: UUID | None,
) -> None:
    user = uuid4()

    response = await _get(_app(site_user), create_dev_login_token(user))

    assert response.status_code == 200
