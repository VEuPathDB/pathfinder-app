from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from pathfinder.main import create_app
from pathfinder.platform.body_limit import RequestBodyLimitMiddleware
from pathfinder.platform.config import Settings, get_settings
from pathfinder.platform.security import RejectNullBytesMiddleware

_LIMIT = 1024


async def _echo_length(request: Request) -> JSONResponse:
    return JSONResponse({"length": len(await request.body())})


def _client() -> httpx.AsyncClient:
    app = Starlette(
        routes=[Route("/echo", _echo_length, methods=["POST"])],
        middleware=[Middleware(RequestBodyLimitMiddleware, max_bytes=_LIMIT)],
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def _chunks(total: int) -> AsyncIterator[bytes]:
    sent = 0
    while sent < total:
        piece = min(256, total - sent)
        sent += piece
        yield b"x" * piece


async def test_a_body_within_the_limit_reaches_the_route_whole() -> None:
    async with _client() as client:
        response = await client.post("/echo", content=b"x" * _LIMIT)

    assert (response.status_code, response.json()) == (200, {"length": _LIMIT})


async def test_a_declared_length_over_the_limit_is_refused() -> None:
    async with _client() as client:
        response = await client.post("/echo", content=b"x" * (_LIMIT + 1))

    assert response.status_code == 413
    assert response.json()["detail"] == "The request body is larger than 1024 bytes."


async def test_a_streamed_body_over_the_limit_is_refused() -> None:
    async with _client() as client:
        response = await client.post("/echo", content=_chunks(_LIMIT * 4))

    assert response.status_code == 413


def test_the_app_limits_a_body_before_any_middleware_reads_it() -> None:
    app = create_app()
    entries = app.user_middleware
    names = [str(entry.cls) for entry in entries]
    limit = names.index(str(RequestBodyLimitMiddleware))

    assert limit < names.index(str(RejectNullBytesMiddleware))
    assert entries[limit].kwargs == {"max_bytes": get_settings().max_request_body_bytes}


def test_the_default_limit_holds_a_message_with_every_attachment() -> None:
    assert Settings.model_fields["max_request_body_bytes"].default == 64 * 1024 * 1024
