"""The development sign-in sets the site cookie and returns under PathFinder."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from pydantic import SecretStr
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.config import get_settings
from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.transport.http.routers import dev_site_login

_BASE = "http://localhost:3000/pathfinder"
_PAGE = f"{_BASE}/plasmodb/conversation"

type Login = tuple[str, str, str, str]


@pytest.fixture(autouse=True)
def _development_account(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", _BASE)
    monkeypatch.setattr(settings, "pathfinder_site", "plasmodb")
    monkeypatch.setattr(settings, "wdk_dev_email", "dev@example.org")
    monkeypatch.setattr(settings, "wdk_dev_password", SecretStr("dev-password"))


def _site_answers(monkeypatch: pytest.MonkeyPatch, answer: str | None) -> list[Login]:
    calls: list[Login] = []

    async def _login(
        site_id: str, email: str, password: str, *, redirect_url: str = "/"
    ) -> str | None:
        calls.append((site_id, email, password, redirect_url))
        return answer

    monkeypatch.setattr(dev_site_login, "password_login", _login)
    return calls


def _site_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    refused = httpx.ConnectError("refused")

    async def _login(*args: object, **kwargs: object) -> str | None:
        del args, kwargs
        raise refused

    monkeypatch.setattr(dev_site_login, "password_login", _login)


async def _sign_in(params: dict[str, str]) -> httpx.Response:
    app = FastAPI()
    app.include_router(dev_site_login.router)
    app.add_exception_handler(
        VEuPathDBError,
        cast(
            "Callable[[Request, Exception], Awaitable[Response]]",
            veupathdb_error_handler,
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/dev/site-login", params=params)


async def test_a_signed_in_account_returns_to_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _site_answers(monkeypatch, "tok")

    response = await _sign_in({"destination": _PAGE})

    assert (response.status_code, response.headers["location"]) == (303, _PAGE)
    assert response.headers.get_list("set-cookie") == [
        "Authorization=tok; Path=/; SameSite=lax"
    ]
    assert calls == [("plasmodb", "dev@example.org", "dev-password", _BASE)]


@pytest.mark.parametrize(
    "params",
    [{"destination": "https://evil.example/x"}, {}],
    ids=["another-host", "no-destination"],
)
async def test_a_destination_outside_pathfinder_returns_to_its_base(
    params: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _site_answers(monkeypatch, "tok")

    response = await _sign_in(params)

    assert (response.status_code, response.headers["location"]) == (303, _BASE)
    assert response.headers.get_list("set-cookie") == [
        "Authorization=tok; Path=/; SameSite=lax"
    ]


async def test_a_refused_account_sets_no_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _site_answers(monkeypatch, None)

    response = await _sign_in({"destination": _PAGE})

    assert response.status_code == 401
    assert response.headers.get_list("set-cookie") == []


async def test_a_site_that_does_not_answer_is_a_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _site_is_down(monkeypatch)

    response = await _sign_in({"destination": _PAGE})

    assert (response.status_code, response.json()["code"]) == (
        503,
        "SITE_UNAVAILABLE",
    )
    assert response.headers.get_list("set-cookie") == []
