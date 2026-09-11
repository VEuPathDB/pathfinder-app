"""What every credentialed test of the served endpoint needs, resolved once."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from veupathdb_mcp import ServiceTokenRegistry

from pathfinder.tests.integration.mcp._served import (
    SERVICE_TOKENS_VARIABLE,
    OwnedStep,
    owned_step_for,
    served_url,
)


@pytest.fixture(scope="session")
def served_endpoint() -> str:
    """The served MCP endpoint, or a skip naming where it was looked for."""
    url = served_url()
    try:
        httpx.get(url, timeout=5.0)
    except httpx.HTTPError:
        pytest.skip(f"veupathdb-wdk-mcp does not answer at {url}")
    return url


@pytest.fixture(scope="session")
def service_bearer(served_endpoint: str) -> str:
    """A secret the served endpoint admits as an application, or a skip."""
    del served_endpoint
    registry = ServiceTokenRegistry.parse(os.environ.get(SERVICE_TOKENS_VARIABLE, ""))
    if not registry.tokens:
        pytest.skip(
            f"service mode needs {SERVICE_TOKENS_VARIABLE}, holding the value the "
            "served container carries"
        )
    return registry.tokens[0].secret


@pytest.fixture
def user_bearer(served_endpoint: str, require_wdk_creds: str) -> str:
    """The registered account's VEuPathDB bearer."""
    del served_endpoint
    return require_wdk_creds


@pytest.fixture
async def owned_step(user_bearer: str) -> AsyncIterator[OwnedStep]:
    async with owned_step_for(user_bearer) as step:
        yield step
