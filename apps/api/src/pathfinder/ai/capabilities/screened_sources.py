"""The tool sources a run opens, each result screened and each call metered as a chat turn's are."""

from __future__ import annotations

from typing import Self

from assistant_core.mcp.declaration import (
    ToolSourceDeclaration,
    ToolSourceDeclarations,
)
from assistant_core.mcp.resolution import ResolvedToolSources
from assistant_core.platform.logging import get_logger

from pathfinder.ai.capabilities.security import tool_output_scan
from pathfinder.platform.metrics import TOOL_SOURCE_ERRORS
from pathfinder.platform.tool_sources import metered_mcp_toolset, source_credential

logger = get_logger(__name__)


class ScreenedToolSources(ResolvedToolSources):
    async def __aenter__(self) -> Self:
        await super().__aenter__()
        for declaration in self.declarations:
            if declaration.name not in self.by_name:
                self._report_unresolved(declaration)
        return self

    def _report_unresolved(self, declaration: ToolSourceDeclaration) -> None:
        admitted = self.admitted.resolve(declaration.source_id) is not None
        TOOL_SOURCE_ERRORS.labels(declaration.source_id, "unresolved").inc()
        logger.warning(
            "Tool source is unavailable this turn",
            tool_source=declaration.name,
            source_id=declaration.source_id,
            reason="did not open" if admitted else "not admitted",
        )


def screened_sources(declarations: ToolSourceDeclarations) -> ScreenedToolSources:
    return ScreenedToolSources(
        declarations=declarations,
        credential=source_credential,
        scan=tool_output_scan(),
        build_toolset=metered_mcp_toolset,
    )
