from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi import APIRouter, FastAPI, Request

from pathfinder.platform.route_templates import (
    TwoTemplatesError,
    install_route_templates,
    route_template,
)

_SEEN: list[str | None] = []


async def _record(request: Request) -> None:
    _SEEN.append(route_template(request.scope))


def _app() -> FastAPI:
    runs = APIRouter()
    runs.add_api_route("", _record, methods=["GET"])
    runs.add_api_route("/{run_id}", _record, methods=["GET"])
    runs.add_api_route("/{run_id}/findings/{finding_id:int}", _record, methods=["GET"])
    audits = APIRouter()
    audits.include_router(runs, prefix="/api/v1/audits")
    own = APIRouter(prefix="/api/v1/conversations")
    own.add_api_route("/{conversation_id}/tasks", _record, methods=["GET"])
    app = FastAPI()
    app.include_router(audits)
    app.include_router(own)
    install_route_templates(app)
    return app


async def test_a_route_under_an_included_prefix_is_named_by_its_full_template() -> None:
    _SEEN.clear()
    run_id = uuid4()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        for path in (
            "/api/v1/audits",
            f"/api/v1/audits/{run_id}",
            f"/api/v1/audits/{run_id}/findings/7",
            f"/api/v1/conversations/{uuid4()}/tasks",
        ):
            assert (await client.get(path)).status_code == 200

    assert _SEEN == [
        "/api/v1/audits",
        "/api/v1/audits/{run_id}",
        "/api/v1/audits/{run_id}/findings/{finding_id}",
        "/api/v1/conversations/{conversation_id}/tasks",
    ]


def test_an_unrouted_scope_has_no_template() -> None:
    app = _app()
    assert [route_template({"type": "http", "path": "/nowhere", "app": app})] == [None]


def test_a_route_included_under_two_templates_is_refused() -> None:
    shared = APIRouter()
    shared.add_api_route("/{run_id}", _record, methods=["GET"])
    app = FastAPI()
    app.include_router(shared, prefix="/api/v1/audits")
    app.include_router(shared, prefix="/api/v1/runs")

    with pytest.raises(TwoTemplatesError) as refused:
        install_route_templates(app)

    assert refused.value.templates == (
        "/api/v1/audits/{run_id}",
        "/api/v1/runs/{run_id}",
    )
