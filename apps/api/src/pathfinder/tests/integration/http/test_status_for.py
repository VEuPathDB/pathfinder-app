"""How the authorization matrix reads a status off a route.

A matrix case must reach one verdict for every route the app serves, whether
that route streams without end or answers slowly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from pathfinder.tests.integration.http._authz_matrix_support import Case, status_for
from pathfinder.tests.integration.http.conftest import client_for, ends_at_first_frame

pytestmark = pytest.mark.asyncio

_SLOW_HANDLER_SECONDS = 16.0
_OK = 200


def _probe_app(finished: list[str]) -> FastAPI:
    app = FastAPI()

    @app.post("/stream")
    async def _stream() -> StreamingResponse:
        async def frames() -> AsyncIterator[bytes]:
            yield b"data: {}\n\n"
            while True:
                await asyncio.sleep(0.05)
                yield b": keep-alive\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream")

    @app.post("/slow")
    async def _slow() -> dict[str, str]:
        await asyncio.sleep(_SLOW_HANDLER_SECONDS)
        finished.append("slow")
        return {"ok": "yes"}

    return app


def _case(path: str) -> Case:
    return Case("POST", path, path, frozenset())


async def test_a_stream_with_no_end_reports_the_status_it_opened_with() -> None:
    """The status line is the answer; the matrix never drains the stream."""
    client = client_for(ends_at_first_frame(_probe_app([])), uuid4())
    async with client:
        status = await asyncio.wait_for(status_for(client, _case("/stream")), timeout=5)

    assert status == _OK


async def test_a_route_that_takes_its_time_answers_and_is_not_cut_short() -> None:
    """A slow handler runs to its end, so its status is the route's own."""
    finished: list[str] = []
    client = client_for(ends_at_first_frame(_probe_app(finished)), uuid4())
    async with client:
        status = await status_for(client, _case("/slow"))

    assert status == _OK
    assert finished == ["slow"], "the handler was cancelled before it answered"
