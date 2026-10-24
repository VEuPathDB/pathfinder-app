"""The tool sources a run opens, each result screened and each call metered as a chat turn's are."""

from __future__ import annotations

from assistant_core.mcp.declaration import ToolSourceDeclarations
from assistant_core.mcp.resolution import ResolvedToolSources

from pathfinder.ai.capabilities.security import tool_output_scan
from pathfinder.platform.tool_sources import metered_mcp_toolset, source_credential


def screened_sources(declarations: ToolSourceDeclarations) -> ResolvedToolSources:
    return ResolvedToolSources(
        declarations=declarations,
        credential=source_credential,
        scan=tool_output_scan(),
        build_toolset=metered_mcp_toolset,
    )
