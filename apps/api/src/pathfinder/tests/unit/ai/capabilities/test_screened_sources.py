from __future__ import annotations

import pytest
from assistant_core.mcp.untrusted import ScanVerdict

from pathfinder.ai.capabilities import screened_sources
from pathfinder.platform.tool_sources import (
    RESEARCH_TOOL_SOURCE,
    metered_mcp_toolset,
    source_credential,
)


async def _scan(text: str) -> ScanVerdict:
    return ScanVerdict(text=text)


def test_a_run_opens_its_sources_screened_metered_and_on_the_deployments_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(screened_sources, "tool_output_scan", lambda: _scan)

    resolved = screened_sources.screened_sources((RESEARCH_TOOL_SOURCE,))

    assert (resolved.declarations, resolved.scan) == ((RESEARCH_TOOL_SOURCE,), _scan)
    assert (resolved.build_toolset, resolved.credential) == (
        metered_mcp_toolset,
        source_credential,
    )
