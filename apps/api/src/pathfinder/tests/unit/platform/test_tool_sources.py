"""Which MCP servers this deployment admits, and what it presents to them."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from assistant_core.mcp.admission import AdmissionRecord
from assistant_core.mcp.resolution import ToolSourceUnavailableError
from veupathdb_mcp.metadata import RESOURCE_NAME
from veupathdb_mcp.server import CONTROL_TESTS_MAX_CALL_SECONDS

from pathfinder.platform.config import get_settings
from pathfinder.platform.tool_sources import (
    WDK_MCP_PART_NAMESPACE,
    WDK_MCP_SOURCE_ID,
    admitted_tool_sources,
    source_credential,
)

ENDPOINT = "http://wdk-mcp:8100/mcp"
TOKEN = "wdk-mcp-client-secret-0123456789abcdef"


@pytest.fixture
def wdk_mcp_admitted(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PATHFINDER_WDK_MCP_URL", ENDPOINT)
    monkeypatch.setenv("PATHFINDER_WDK_MCP_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_wdk_mcp(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PATHFINDER_WDK_MCP_URL", "")
    monkeypatch.setenv("PATHFINDER_WDK_MCP_TOKEN", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_a_deployment_that_names_no_endpoint_admits_nothing(
    no_wdk_mcp: None,
) -> None:
    del no_wdk_mcp

    assert admitted_tool_sources().records == ()


def test_the_wdk_server_is_admitted_at_the_endpoint_it_is_given(
    wdk_mcp_admitted: None,
) -> None:
    del wdk_mcp_admitted

    record = admitted_tool_sources().resolve(WDK_MCP_SOURCE_ID)

    assert record is not None
    assert record.endpoint == ENDPOINT
    assert record.credential_mode == "service"
    assert record.part_namespace == WDK_MCP_PART_NAMESPACE
    assert record.approval_policy == "annotations"


def test_the_admitted_id_is_the_name_the_server_publishes() -> None:
    """One id names the server, so a declaration cannot miss it by a letter."""
    assert WDK_MCP_SOURCE_ID == RESOURCE_NAME


def test_the_call_budget_covers_the_longest_call_the_server_declares(
    wdk_mcp_admitted: None,
) -> None:
    del wdk_mcp_admitted

    record = admitted_tool_sources().resolve(WDK_MCP_SOURCE_ID)

    assert record is not None
    assert record.max_call_seconds >= CONTROL_TESTS_MAX_CALL_SECONDS


def test_the_configured_credential_is_the_one_presented(
    wdk_mcp_admitted: None,
) -> None:
    del wdk_mcp_admitted
    record = admitted_tool_sources().resolve(WDK_MCP_SOURCE_ID)
    assert record is not None

    assert source_credential(record) == TOKEN


def test_an_endpoint_without_its_credential_admits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Half a configuration admits no server, rather than calling it bare."""
    monkeypatch.setenv("PATHFINDER_WDK_MCP_URL", ENDPOINT)
    monkeypatch.setenv("PATHFINDER_WDK_MCP_TOKEN", "")
    get_settings.cache_clear()

    assert admitted_tool_sources().records == ()

    get_settings.cache_clear()


def test_an_unconfigured_credential_is_refused_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATHFINDER_WDK_MCP_TOKEN", "")
    get_settings.cache_clear()
    record = AdmissionRecord(
        source_id=WDK_MCP_SOURCE_ID,
        endpoint=ENDPOINT,
        credential_mode="service",
        part_namespace=WDK_MCP_PART_NAMESPACE,
    )

    with pytest.raises(ToolSourceUnavailableError, match="PATHFINDER_WDK_MCP_TOKEN"):
        source_credential(record)

    get_settings.cache_clear()


def test_a_source_this_deployment_holds_no_credential_for_is_refused() -> None:
    record = AdmissionRecord(
        source_id="eda",
        endpoint="https://eda.example.org/mcp",
        credential_mode="service",
        part_namespace="eda",
    )

    with pytest.raises(ToolSourceUnavailableError, match="eda"):
        source_credential(record)
