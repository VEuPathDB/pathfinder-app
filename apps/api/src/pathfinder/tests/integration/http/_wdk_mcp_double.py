"""A stand-in for veupathdb-wdk-mcp, and what a test needs to drive it.

The double answers under the served server's own tool names and annotations,
so the path a declaration takes to reach the agent is exercised over a socket.
The served server's live behaviour is proven by its own integration lane.
Beside it: how a test serves an MCP source, how this deployment admits one,
and how one site-help turn runs against it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from socket import socket
from typing import Any
from uuid import UUID

import pytest
import uvicorn
from assistant_core.mcp.admission import (
    AdmissionRecord,
    AdmittedSources,
    install_admitted_sources,
)
from fastapi import FastAPI
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from procrastinate.testing import InMemoryConnector

from pathfinder.platform.config import get_settings
from pathfinder.platform.tool_sources import (
    WDK_MCP_PART_NAMESPACE,
    WDK_MCP_SOURCE_ID,
)
from pathfinder.tests.integration.chat._helpers import (
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for

SITE_HELP = "site_help"
SERVICE_TOKEN = "wdk-mcp-client-secret-0123456789abcdef"
CALL_SECONDS = 30

RECORD_TYPES = ["transcript", "organism"]
SEARCH_NAMES = ["GenesByMolecularWeight", "GenesByTaxon"]
CONTROL_TEST_RESULT = "2 of 2 positive controls returned"

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ADDITIVE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=False,
)


async def list_record_types(site_id: str) -> list[str]:
    """Report the record types one site serves.

    Args:
        site_id: VEuPathDB site, for example 'plasmodb'.
    """
    del site_id
    return RECORD_TYPES


async def search_for_searches(site_id: str, query: str) -> list[str]:
    """Report the searches whose subject matches a query.

    Args:
        site_id: VEuPathDB site, for example 'plasmodb'.
        query: What the searches should be about.
    """
    del site_id, query
    return SEARCH_NAMES


async def run_control_tests_on_search(
    site_id: str,
    target_search_name: str,
    target_parameters: dict[str, Any],
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
    record_type: str = "transcript",
) -> str:
    """Intersect a search's results with known control genes.

    Args:
        site_id: VEuPathDB site, for example 'plasmodb'.
        target_search_name: WDK search urlSegment to test.
        target_parameters: Parameter values, each in its typed shape.
        positive_controls: Gene ids the search should return.
        negative_controls: Gene ids the search should not return.
        record_type: Record type. Gene searches are 'transcript'.
    """
    del site_id, target_search_name, target_parameters
    del positive_controls, negative_controls, record_type
    return CONTROL_TEST_RESULT


ANNOTATIONS: dict[str, ToolAnnotations] = {
    "list_record_types": READ,
    "search_for_searches": READ,
    "run_control_tests_on_search": ADDITIVE_WRITE,
}


def build_double() -> FastMCP[None]:
    """The three tools site help declares, under the names the server serves."""
    server: FastMCP[None] = FastMCP(name="veupathdb-wdk-mcp-double")
    for tool in (list_record_types, search_for_searches, run_control_tests_on_search):
        server.tool(tool, annotations=ANNOTATIONS[tool.__name__])
    return server


class _AnnouncingServer(uvicorn.Server):
    """Announces the moment its socket is bound and its app has started."""

    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self.ready = asyncio.Event()

    async def startup(self, sockets: list[socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        self.ready.set()

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        """An in-process test server must not install process signal handlers."""
        yield


@asynccontextmanager
async def serve_mcp(source: FastMCP[None]) -> AsyncIterator[str]:
    """Serve one MCP server on a port the operating system picks."""
    app = source.http_app(path="/mcp", stateless_http=True)
    server = _AnnouncingServer(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"),
    )
    task = asyncio.create_task(server.serve())
    try:
        await server.ready.wait()
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task


@asynccontextmanager
async def served_double() -> AsyncIterator[str]:
    """Serve the double. Yields its URL."""
    async with serve_mcp(build_double()) as endpoint:
        yield endpoint


@contextmanager
def admit_wdk_mcp(endpoint: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Admit one served endpoint under the id site help declares."""
    install_admitted_sources(
        AdmittedSources(
            records=(
                AdmissionRecord(
                    source_id=WDK_MCP_SOURCE_ID,
                    endpoint=endpoint,
                    credential_mode="service",
                    part_namespace=WDK_MCP_PART_NAMESPACE,
                    max_call_seconds=CALL_SECONDS,
                ),
            ),
        ),
    )
    monkeypatch.setenv("PATHFINDER_WDK_MCP_TOKEN", SERVICE_TOKEN)
    get_settings.cache_clear()
    try:
        yield endpoint
    finally:
        install_admitted_sources(AdmittedSources())
        get_settings.cache_clear()


async def run_site_help_turn(
    app: FastAPI,
    user_id: UUID,
    connector: InMemoryConnector,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    """Post one site-help body, run the deferred turn, and return its chunks."""
    queued = len(chat_turn_jobs(connector))
    async with client_for(app, user_id) as client:
        task = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=60.0),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(connector, queued),
            timeout=10.0,
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(task, timeout=60.0)
    if response.status_code != 200:
        msg = f"chat returned {response.status_code}; body={response.text[:500]!r}"
        raise AssertionError(msg)
    return parse_sse_body(response.text)
