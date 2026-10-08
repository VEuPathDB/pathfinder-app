"""The dev-login credential exists only under the mock overlay.

The site sign-in route mounts only in development with the dev account set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

import pathfinder
from pathfinder.main import create_app
from pathfinder.platform.config import get_settings
from pathfinder.tests._support.routes import api_routes
from pathfinder.transport.http.routers import dev, dev_site_login

_MINTER = "create_dev_login_token"
_SITE_LOGIN = "/api/v1/dev/site-login"
_ALLOWED_MINTERS = {
    Path("platform/security.py"),
    Path("transport/http/routers/dev.py"),
}


def _endpoints(*, include_dev_routes: bool) -> set[object]:
    app = create_app(include_dev_routes=include_dev_routes)
    return {route.endpoint for route in api_routes(app.routes)}


def test_the_production_app_has_no_dev_login_route() -> None:
    assert dev.dev_login not in _endpoints(include_dev_routes=False)


def test_the_overlay_app_does_have_it() -> None:
    assert dev.dev_login in _endpoints(include_dev_routes=True)


def test_only_the_dev_router_mints_a_dev_login_token() -> None:
    root = Path(pathfinder.__file__).parent
    minters = {
        source.relative_to(root)
        for source in root.rglob("*.py")
        if not source.is_relative_to(root / "tests") and _MINTER in source.read_text()
    }

    assert minters == _ALLOWED_MINTERS


def _site_login_endpoints(
    monkeypatch: pytest.MonkeyPatch, api_env: str, email: str, password: str
) -> list[object]:
    settings = get_settings()
    monkeypatch.setattr(settings, "api_env", api_env)
    monkeypatch.setattr(settings, "wdk_dev_email", email)
    monkeypatch.setattr(settings, "wdk_dev_password", SecretStr(password))
    return [
        route.endpoint
        for route in api_routes(create_app(include_dev_routes=False).routes)
        if route.path == _SITE_LOGIN
    ]


@pytest.mark.parametrize(
    ("api_env", "email", "password"),
    [
        ("production", "dev@example.org", "dev-password"),
        ("development", "", ""),
        ("development", "dev@example.org", ""),
    ],
    ids=["production", "development-without-account", "development-without-password"],
)
def test_the_site_login_route_is_not_mounted(
    api_env: str, email: str, password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _site_login_endpoints(monkeypatch, api_env, email, password) == []


def test_development_with_the_dev_account_mounts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _site_login_endpoints(
        monkeypatch, "development", "dev@example.org", "dev-password"
    ) == [dev_site_login.site_login]
