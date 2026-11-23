from __future__ import annotations

from collections.abc import Iterator

import pytest
from veupathdb_mcp.catalog import (
    SearchMatch,
    post_decision,
    use_decisions_transport,
)
from veupathdb_mcp.testing import offline_decisions

from strategist.tests._support.universal_searches import TEXT_SEARCH


async def _universal(
    _site_id: str, _record_type: str | list[str] | None
) -> tuple[SearchMatch, ...]:
    return (TEXT_SEARCH,)


@pytest.fixture(autouse=True)
def a_scripted_flow_reads_no_service(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        "strategist.ai.tools.standalone.catalog.universal_searches", _universal
    )
    use_decisions_transport(offline_decisions)
    yield
    use_decisions_transport(post_decision)
