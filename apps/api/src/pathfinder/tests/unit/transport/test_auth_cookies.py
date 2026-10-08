"""PathFinder keeps its own session under its base path and leaves the website login alone."""

from __future__ import annotations

import ast
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI
from veupathdb.wdk import WDKUserInfo

import pathfinder
from pathfinder.main import create_app
from pathfinder.platform.config import get_settings
from pathfinder.platform.readiness import reset_readiness
from pathfinder.platform.security import create_user_token
from pathfinder.services import wdk_identity
from pathfinder.tests._support.routes import api_routes
from pathfinder.transport.http.routers import dev
from pathfinder.transport.http.routers.veupathdb_auth import router

_AUTH = "/api/v1/veupathdb/auth"
_SITE_LOGIN_WRITER = Path("transport/http/routers/dev_site_login.py")
_SESSION_SCOPE = ["HttpOnly", "Path=/pathfinder", "SameSite=lax", "Secure"]


def _scope(header: str) -> list[str]:
    """The attributes of a cookie header, without its value or expiry."""
    return sorted(
        part
        for part in header.split("; ")[1:]
        if not part.startswith(("expires=", "Max-Age="))
    )


def test_pathfinder_neither_signs_in_nor_signs_out() -> None:
    routes = api_routes(create_app(include_dev_routes=False).routes)
    auth = sorted(
        pair for route in routes if route.path.startswith(_AUTH) for pair in route.pairs
    )

    assert auth == [
        ("GET", f"{_AUTH}/status"),
        ("POST", f"{_AUTH}/refresh"),
    ]


async def test_dev_login_scopes_its_session_to_the_base_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _user_id(session: object, external_id: str) -> UUID:
        del session, external_id
        return uuid4()

    async def _db() -> AsyncGenerator[None]:
        yield None

    monkeypatch.setattr(dev, "get_or_create_user_id", _user_id)
    app = FastAPI()
    app.include_router(dev.router)
    app.dependency_overrides[get_db_session] = _db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/dev/login")

    written = response.headers.get_list("set-cookie")
    assert [entry.split("=", 1)[0] for entry in written] == ["pathfinder-auth"]
    assert _scope(written[0]) == _SESSION_SCOPE


def _names_the_site_login(key: ast.expr) -> bool:
    match key:
        case ast.Constant(value="Authorization"):
            return True
    return False


def _writes_the_site_login(node: ast.AST) -> bool:
    match node:
        case ast.Call(func=ast.Attribute(attr="set_cookie" | "delete_cookie")):
            keys = [
                *node.args[:1],
                *(kw.value for kw in node.keywords if kw.arg == "key"),
            ]
            return any(_names_the_site_login(key) for key in keys)
    return False


def test_only_the_development_sign_in_writes_the_website_login_cookie() -> None:
    root = Path(pathfinder.__file__).parent
    writers = {
        source.relative_to(root)
        for source in root.rglob("*.py")
        if not source.is_relative_to(root / "tests")
        and any(
            _writes_the_site_login(node)
            for node in ast.walk(ast.parse(source.read_text()))
        )
    }

    assert writers == {_SITE_LOGIN_WRITER}


def _names_the_session_cookie(node: ast.AST) -> bool:
    match node:
        case ast.Constant(value="pathfinder-auth"):
            return True
    return False


def test_only_the_security_module_names_the_session_cookie() -> None:
    root = Path(pathfinder.__file__).parent
    namers = {
        source.relative_to(root)
        for source in root.rglob("*.py")
        if not source.is_relative_to(root / "tests")
        and any(
            _names_the_session_cookie(node)
            for node in ast.walk(ast.parse(source.read_text()))
        )
    }

    assert namers == {Path("platform/security.py")}


@pytest.fixture
def _real_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PATHFINDER_CHAT_PROVIDER", "default")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-unit-test-only")
    get_settings.cache_clear()
    reset_readiness()
    yield
    get_settings.cache_clear()


def _site_answers(monkeypatch: pytest.MonkeyPatch, user: WDKUserInfo | None) -> None:
    async def _fetch(site_id: str) -> WDKUserInfo | None:
        del site_id
        return user

    monkeypatch.setattr(wdk_identity, "fetch_current_user", _fetch)


async def _status(cookies: dict[str, str]) -> httpx.Response:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies=cookies
    ) as client:
        return await client.get(
            "/api/v1/veupathdb/auth/status", params={"siteId": "plasmodb"}
        )


def _session() -> dict[str, str]:
    return {"pathfinder-auth": create_user_token(uuid4())}


_SIGNED_OUT = {"signedIn": False}


@pytest.mark.usefixtures("_real_provider")
@pytest.mark.parametrize(
    "user",
    [None, WDKUserInfo(id=9, is_guest=True, email=None)],
    ids=["refused-token", "guest"],
)
async def test_a_signed_out_status_clears_the_pathfinder_session(
    user: WDKUserInfo | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _site_answers(monkeypatch, user)

    response = await _status(_session())

    cleared = response.headers.get_list("set-cookie")
    assert response.json()["signedIn"] is False
    assert [c.split(";")[0] for c in cleared] == ['pathfinder-auth=""']
    assert _scope(cleared[0]) == _SESSION_SCOPE


@pytest.mark.usefixtures("_real_provider")
async def test_a_signed_out_status_without_a_session_sets_no_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _site_answers(monkeypatch, None)

    response = await _status({})

    assert response.json() == _SIGNED_OUT
    assert "set-cookie" not in response.headers


@pytest.mark.usefixtures("_real_provider")
async def test_a_signed_in_status_keeps_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _site_answers(
        monkeypatch, WDKUserInfo(id=7, is_guest=False, email="researcher@upenn.edu")
    )

    response = await _status(_session())

    assert response.json() == {"signedIn": True}
    assert "set-cookie" not in response.headers


async def test_a_mock_provider_reads_a_session_cookie_as_signed_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATHFINDER_CHAT_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        response = await _status(_session())
    finally:
        get_settings.cache_clear()

    assert response.json() == {"signedIn": True}
