from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from veupathdb.wdk import get_site

from pathfinder.platform.config import get_settings
from pathfinder.transport.http.routers import health


async def _config() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(health.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/config")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def test_the_config_names_the_deployment_site() -> None:
    body = await _config()

    assert body["siteId"] == get_settings().pathfinder_site


async def test_the_sign_in_url_is_the_sites_login_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "pathfinder_site", "plasmodb")

    body = await _config()

    assert body["siteId"] == "plasmodb"
    assert (
        body["siteSignInUrl"] == f"{get_site('plasmodb').web_base_url}/app/user/login"
    )


def _development(monkeypatch: pytest.MonkeyPatch, email: str, password: str) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "api_env", "development")
    monkeypatch.setattr(settings, "pathfinder_site", "plasmodb")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:3000/pathfinder")
    monkeypatch.setattr(settings, "wdk_dev_email", email)
    monkeypatch.setattr(settings, "wdk_dev_password", SecretStr(password))


async def test_development_with_the_dev_account_signs_in_through_the_dev_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _development(monkeypatch, "dev@example.org", "dev-password")

    body = await _config()

    assert (
        body["siteSignInUrl"]
        == "http://localhost:3000/pathfinder/api/v1/dev/site-login"
    )


async def test_development_without_the_dev_account_signs_in_on_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _development(monkeypatch, "", "")

    body = await _config()

    assert (
        body["siteSignInUrl"] == f"{get_site('plasmodb').web_base_url}/app/user/login"
    )
