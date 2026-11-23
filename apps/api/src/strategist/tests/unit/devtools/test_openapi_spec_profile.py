"""The generated spec is the production contract, whatever the process env."""

from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import SecretStr

from strategist.devtools.openapi import (
    DevRouteInSpecError,
    _refuse_dev_routes,
    _spec_with_stable_overrides,
    _SpecPaths,
    generate_openapi_json,
)
from strategist.main import create_app
from strategist.platform.config import get_settings
from strategist.transport.http.routers import dev_site_login
from strategist.transport.http.routers.dev_site_login import DEV_ROUTE_PREFIX
from strategist_scripted.dev_routes import router as scripted_dev_router

DEV_LOGIN = "/api/v1/dev/login"


def test_the_spec_never_carries_dev_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "strategist_chat_provider", "mock")

    spec = _spec_with_stable_overrides()

    paths = _SpecPaths.model_validate(spec).paths
    dev_paths = [p for p in paths if p.startswith("/api/v1/dev/")]
    assert dev_paths == []


def test_every_dev_route_lies_under_the_dev_prefix() -> None:
    paths = sorted(
        route.path
        for router in (scripted_dev_router, dev_site_login.router)
        for route in router.routes
        if isinstance(route, APIRoute)
    )

    assert paths == [
        "/api/v1/dev/audits/sample",
        DEV_LOGIN,
        "/api/v1/dev/site-login",
    ]
    assert {path.removeprefix(DEV_ROUTE_PREFIX)[:1] for path in paths} == {"/"}


def test_a_spec_naming_the_site_login_is_refused() -> None:
    with pytest.raises(DevRouteInSpecError):
        _refuse_dev_routes({"paths": {"/api/v1/dev/site-login": {}}})


def test_a_spec_naming_a_dev_route_is_refused_by_name() -> None:
    with pytest.raises(DevRouteInSpecError) as raised:
        _refuse_dev_routes({"paths": {DEV_LOGIN: {}, "/api/v1/conversations": {}}})

    assert DEV_LOGIN in str(raised.value)
    assert "/api/v1/conversations" not in str(raised.value)


def test_nothing_is_written_when_the_app_mounts_a_dev_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "strategist.devtools.openapi.create_app",
        lambda *, include_dev_routes=None: create_app(include_dev_routes=True),
    )
    out_path = tmp_path / "openapi.json"

    with pytest.raises(DevRouteInSpecError):
        generate_openapi_json(out_path=out_path)

    assert not out_path.exists()


def test_local_development_adds_no_route_to_the_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "api_env", "development")
    monkeypatch.setattr(settings, "wdk_dev_email", "dev@example.org")
    monkeypatch.setattr(settings, "wdk_dev_password", SecretStr("dev-password"))

    spec = _spec_with_stable_overrides()

    paths = _SpecPaths.model_validate(spec).paths
    assert [p for p in paths if p.startswith("/api/v1/dev/")] == []
