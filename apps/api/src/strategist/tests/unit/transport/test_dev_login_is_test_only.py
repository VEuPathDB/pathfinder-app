"""The dev-login credential exists only under the mock overlay.

The site sign-in route mounts only in development with the dev account set.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

import strategist
from strategist.main import create_app
from strategist.platform.config import get_settings
from strategist.platform.security import SessionToken, decode_session_token
from strategist.tests._support.routes import api_routes
from strategist.transport.http.routers import dev_site_login
from strategist_scripted import dev_routes
from strategist_scripted.dev_login import create_dev_login_token

_MINTING = ("create_dev_login_token", "set_dev_login_cookie", "dev_login=True")
_SITE_LOGIN = "/api/v1/dev/site-login"


def _endpoints(*, include_dev_routes: bool) -> set[object]:
    app = create_app(include_dev_routes=include_dev_routes)
    return {route.endpoint for route in api_routes(app.routes)}


def test_the_production_app_has_no_dev_login_route() -> None:
    assert dev_routes.dev_login not in _endpoints(include_dev_routes=False)


def test_the_production_app_has_no_sample_audit_route() -> None:
    assert (
        _endpoints(include_dev_routes=False) & {dev_routes.store_sample_audit_run}
        == set()
    )


def test_the_overlay_app_does_have_it() -> None:
    assert dev_routes.dev_login in _endpoints(include_dev_routes=True)


def test_no_production_module_mints_a_dev_login_token() -> None:
    root = Path(strategist.__file__).parent
    minters = sorted(
        source.relative_to(root).as_posix()
        for source in root.rglob("*.py")
        if not source.is_relative_to(root / "tests")
        and any(name in source.read_text() for name in _MINTING)
    )

    assert minters == []


def test_the_scripted_minter_signs_the_claims_production_reads() -> None:
    user = uuid4()

    claims = decode_session_token(create_dev_login_token(user))

    assert claims == SessionToken(sub=user, dev_login=True)


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
