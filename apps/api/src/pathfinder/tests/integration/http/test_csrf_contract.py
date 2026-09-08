"""Contract test for the CSRF middleware.

It uses a client without the default CSRF header, and asserts that every
state-changing route is rejected before its handler runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from pathfinder.tests._support.routes import api_routes

_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
_EXPECTED_DETAIL = "Missing required X-Requested-With header"


@pytest.fixture
async def unheaded_client(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """An httpx client with no default headers."""
    del patch_app_db_engine, db_cleaner
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as c:
        yield c


def _state_changing_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Yield ``(method, path)`` for every POST/PUT/PATCH/DELETE on the app."""
    out: list[tuple[str, str]] = []
    for route in api_routes(app.routes):
        for method in route.methods:
            if method in _SAFE_METHODS:
                continue
            out.append((method, route.path))
    return out


@pytest.mark.asyncio
async def test_every_state_changing_route_rejects_missing_csrf_header(
    unheaded_client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    """Every state-changing method must return 403 when the CSRF header is absent."""
    routes = _state_changing_routes(app)
    # An empty sweep would pass without testing anything.
    assert len(routes) >= 5, routes

    failures: list[str] = []
    for method, path in routes:
        # A path-param placeholder gives a 404 at routing time. Substitute a
        # valid UUID to keep the request on the real dispatch path.
        concrete = path
        while "{" in concrete:
            start = concrete.index("{")
            end = concrete.index("}", start)
            concrete = (
                concrete[:start]
                + "00000000-0000-0000-0000-000000000000"
                + concrete[end + 1 :]
            )
        resp = await unheaded_client.request(method, concrete)
        if resp.status_code != 403:
            failures.append(
                f"{method} {path} -> {resp.status_code} (expected 403); "
                f"body={resp.text[:200]!r}",
            )
            continue
        body = resp.json()
        if body.get("detail") != _EXPECTED_DETAIL:
            failures.append(
                f"{method} {path} -> 403 but detail={body.get('detail')!r} "
                f"(expected {_EXPECTED_DETAIL!r})",
            )

    assert not failures, "\n".join(failures)


@pytest.mark.asyncio
async def test_safe_methods_bypass_csrf_middleware(
    unheaded_client: httpx.AsyncClient,
) -> None:
    """The CSRF middleware gates state-changing requests only."""
    resp = await unheaded_client.get("/api/v1/sites")
    assert resp.status_code != 403, resp.text
    if resp.status_code == 403:
        body = resp.json()
        assert body.get("detail") != _EXPECTED_DETAIL
