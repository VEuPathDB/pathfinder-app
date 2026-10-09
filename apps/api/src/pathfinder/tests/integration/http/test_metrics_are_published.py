from __future__ import annotations

import socket
import urllib.request
from collections.abc import Iterator
from uuid import uuid4
from wsgiref.simple_server import WSGIServer

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.metrics import serve_metrics
from pathfinder.tests.integration.http.conftest import (
    chat_body,
    chat_jobs,
    client_for,
    ends_at_first_frame,
    make_user,
)

_STARTED = 'pathfinder_chat_turns_started_total{assistant="pathfinder"}'
_CHAT_REQUESTS = (
    'pathfinder_http_requests_total{method="POST",route="/api/v1/chat",status="2xx"}'
)


@pytest.fixture
def metrics_server() -> Iterator[WSGIServer]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    server = serve_metrics(port, "127.0.0.1")
    assert server is not None
    yield server
    server.shutdown()
    server.server_close()


def _scrape(server: WSGIServer) -> dict[str, float]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{server.server_port}/metrics"
    ) as reply:
        body = reply.read().decode()
    series: dict[str, float] = {}
    for line in body.splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.rpartition(" ")
            series[name] = float(value)
    return series


async def test_a_served_turn_shows_in_the_scrape(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
    metrics_server: WSGIServer,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    before = _scrape(metrics_server)
    owner = await make_user(db_session)

    async with client_for(ends_at_first_frame(app), owner.id) as client:
        response = await client.post("/api/v1/chat", json=chat_body(uuid4()))

    after = _scrape(metrics_server)
    assert response.status_code == 200
    assert len(chat_jobs(in_memory_jobs)) == 1
    assert after[_STARTED] == before.get(_STARTED, 0.0) + 1
    assert after[_CHAT_REQUESTS] == before.get(_CHAT_REQUESTS, 0.0) + 1
