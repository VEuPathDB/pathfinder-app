"""The auth status of a degraded site is read on a site that answers.

The app shell blocks on this route, so reading a site with no loaded catalog
would hold the shell for the WDK client's whole retry ladder.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from assistant_core.platform.db import get_db_session
from fastapi import FastAPI
from veupathdb.wdk.wdk_models import WDKUserInfo

from pathfinder.platform.readiness import get_readiness, reset_readiness
from pathfinder.platform.security import limiter
from pathfinder.transport.http.routers.veupathdb_auth import router


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_readiness()


def _app(monkeypatch: pytest.MonkeyPatch, seen: list[str]) -> FastAPI:
    async def _fetch(site_id: str) -> WDKUserInfo:
        seen.append(site_id)
        return WDKUserInfo(id=7, isGuest=False, email="researcher@upenn.edu")

    monkeypatch.setattr(
        "pathfinder.transport.http.routers.veupathdb_auth.fetch_current_user", _fetch
    )

    async def _session() -> AsyncGenerator[None]:
        yield None

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.dependency_overrides[get_db_session] = _session
    return app


async def _status(app: FastAPI, site_id: str) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/veupathdb/auth/status", params={"siteId": site_id}
        )
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def test_a_degraded_site_reads_the_account_on_a_loaded_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = get_readiness()
    readiness.mark_catalog_failed("veupathdb", "TimeoutError")
    readiness.mark_catalog_ready("plasmodb")
    seen: list[str] = []

    body = await _status(_app(monkeypatch, seen), "veupathdb")

    assert seen == ["plasmodb"]
    assert body["signedIn"] is True
    assert body["email"] == "researcher@upenn.edu"


async def test_a_loaded_site_reads_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    get_readiness().mark_catalog_ready("plasmodb")
    seen: list[str] = []

    body = await _status(_app(monkeypatch, seen), "plasmodb")

    assert seen == ["plasmodb"]
    assert body["signedIn"] is True
