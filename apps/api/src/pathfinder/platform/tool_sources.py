"""The MCP servers this deployment admits, and the credential it presents."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from assistant_core.mcp.admission import AdmissionRecord, AdmittedSources
from assistant_core.mcp.resolution import ToolSourceUnavailableError

from pathfinder.platform.config import Settings, get_settings

WDK_MCP_SOURCE_ID = "veupathdb-wdk-mcp"
WDK_MCP_PART_NAMESPACE = "wdk"

# The budget covers the longest call the served tools declare, so a control
# run is not cut off by the client.
WDK_MCP_CALL_SECONDS = 180

RESEARCH_MCP_SOURCE_ID = "veupathdb-research-mcp"
RESEARCH_MCP_PART_NAMESPACE = "research"
RESEARCH_MCP_CALL_SECONDS = 60

# The setting that holds each admitted server's credential, and the variable a
# refusal names. A source id absent here is one this deployment cannot call.
_CREDENTIALS: Mapping[str, tuple[Callable[[Settings], str], str]] = {
    WDK_MCP_SOURCE_ID: (
        lambda settings: settings.pathfinder_wdk_mcp_token,
        "PATHFINDER_WDK_MCP_TOKEN",
    ),
    RESEARCH_MCP_SOURCE_ID: (
        lambda settings: settings.pathfinder_research_mcp_token,
        "PATHFINDER_RESEARCH_MCP_TOKEN",
    ),
}


def _record(
    *,
    source_id: str,
    endpoint: str,
    token: str,
    part_namespace: str,
    max_call_seconds: int,
) -> AdmissionRecord | None:
    """One admitted server, or nothing when half its configuration is missing."""
    if not endpoint.strip() or not token.strip():
        return None
    return AdmissionRecord(
        source_id=source_id,
        endpoint=endpoint.strip(),
        credential_mode="service",
        part_namespace=part_namespace,
        max_call_seconds=max_call_seconds,
    )


def admitted_tool_sources() -> AdmittedSources:
    """Every server this deployment admits.

    A server is admitted once its endpoint and the credential it takes are
    both configured, so a call never leaves without one.
    """
    settings = get_settings()
    candidates = (
        _record(
            source_id=WDK_MCP_SOURCE_ID,
            endpoint=settings.pathfinder_wdk_mcp_url,
            token=settings.pathfinder_wdk_mcp_token,
            part_namespace=WDK_MCP_PART_NAMESPACE,
            max_call_seconds=WDK_MCP_CALL_SECONDS,
        ),
        _record(
            source_id=RESEARCH_MCP_SOURCE_ID,
            endpoint=settings.pathfinder_research_mcp_url,
            token=settings.pathfinder_research_mcp_token,
            part_namespace=RESEARCH_MCP_PART_NAMESPACE,
            max_call_seconds=RESEARCH_MCP_CALL_SECONDS,
        ),
    )
    return AdmittedSources(
        records=tuple(record for record in candidates if record is not None),
    )


def source_credential(record: AdmissionRecord) -> str | None:
    """The credential this deployment presents to one admitted server."""
    held = _CREDENTIALS.get(record.source_id)
    if held is None:
        msg = f"this deployment holds no credential for {record.source_id!r}"
        raise ToolSourceUnavailableError(msg)
    read, variable = held
    token = read(get_settings()).strip()
    if not token:
        msg = f"{variable} must carry a credential {record.source_id!r} accepts."
        raise ToolSourceUnavailableError(msg)
    return token


__all__ = [
    "RESEARCH_MCP_CALL_SECONDS",
    "RESEARCH_MCP_PART_NAMESPACE",
    "RESEARCH_MCP_SOURCE_ID",
    "WDK_MCP_CALL_SECONDS",
    "WDK_MCP_PART_NAMESPACE",
    "WDK_MCP_SOURCE_ID",
    "admitted_tool_sources",
    "source_credential",
]
