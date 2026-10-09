from __future__ import annotations

import socket
import urllib.request
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from pathfinder.main import create_app
from pathfinder.platform.metrics import HttpMetricsMiddleware, serve_metrics

_REQUESTS = "pathfinder_http_requests_total"
_LATENCY_COUNT = "pathfinder_http_request_duration_seconds_count"


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe/things/{thing_id}")
    async def thing(thing_id: int) -> dict[str, int]:
        return {"id": thing_id}

    app.add_middleware(HttpMetricsMiddleware)
    return app


async def _get(app: FastAPI, path: str) -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    return response.status_code


async def test_a_request_counts_under_its_route_template() -> None:
    labels = {"method": "GET", "route": "/probe/things/{thing_id}", "status": "2xx"}
    before = _sample(_REQUESTS, labels)

    assert await _get(_app(), "/probe/things/42") == 200

    assert _sample(_REQUESTS, labels) == before + 1
    assert _sample(_REQUESTS, {**labels, "route": "/probe/things/42"}) == 0.0


async def test_a_request_records_its_latency_under_the_template() -> None:
    labels = {"method": "GET", "route": "/probe/things/{thing_id}"}
    before = _sample(_LATENCY_COUNT, labels)

    await _get(_app(), "/probe/things/7")

    assert _sample(_LATENCY_COUNT, labels) == before + 1


async def test_a_refused_request_counts_by_its_status_class() -> None:
    labels = {"method": "GET", "route": "/probe/things/{thing_id}", "status": "4xx"}
    before = _sample(_REQUESTS, labels)

    assert await _get(_app(), "/probe/things/not-a-number") == 422

    assert _sample(_REQUESTS, labels) == before + 1


async def test_a_path_no_route_matches_counts_under_one_label() -> None:
    labels = {"method": "GET", "route": "unmatched", "status": "4xx"}
    before = _sample(_REQUESTS, labels)

    assert await _get(_app(), "/probe/nothing/here/91") == 404

    assert _sample(_REQUESTS, labels) == before + 1


def test_port_zero_serves_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple[int, str]] = []
    monkeypatch.setattr(
        "pathfinder.platform.metrics.start_http_server",
        lambda port, addr: started.append((port, addr)),
    )

    assert (serve_metrics(0, "127.0.0.1"), started) == (None, [])


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


@pytest.mark.allow_network
def test_the_server_answers_the_text_format_on_its_port_and_address() -> None:
    port = _free_port()
    server = serve_metrics(port, "127.0.0.1")
    assert server is not None
    assert server.server_address == ("127.0.0.1", port)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics") as reply:
            content_type = reply.headers["Content-Type"]
            body = reply.read().decode()
    finally:
        server.shutdown()
        server.server_close()

    assert content_type.startswith("text/plain; version=")
    assert "# TYPE pathfinder_chat_turns_finished_total counter" in body


async def test_the_app_serves_no_metrics_route() -> None:
    app = create_app(include_dev_routes=False)

    assert await _get(app, "/metrics") == 404
    assert "/metrics" not in app.openapi()["paths"]


async def test_the_app_counts_its_requests_under_their_templates() -> None:
    app = create_app(include_dev_routes=False)
    labels = {
        "method": "GET",
        "route": "/api/v1/conversations/{strategyId:uuid}",
        "status": "4xx",
    }
    before = _sample(_REQUESTS, labels)

    assert await _get(app, f"/api/v1/conversations/{uuid4()}") == 401

    assert _sample(_REQUESTS, labels) == before + 1
