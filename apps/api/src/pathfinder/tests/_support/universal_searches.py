from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import SearchMatch

TEXT_SEARCH = SearchMatch(
    name="GenesByText",
    display_name="Gene Text Search",
    description="Search all text fields for genes matching a keyword or phrase.",
    record_type="transcript",
    category="general",
    returns="transcript",
)


@pytest.fixture(autouse=True)
def serve_the_text_search_as_universal(monkeypatch: pytest.MonkeyPatch) -> None:
    async def served(
        _site_id: str, _record_type: str | list[str] | None
    ) -> tuple[SearchMatch, ...]:
        return (TEXT_SEARCH,)

    monkeypatch.setattr(
        "pathfinder.ai.tools.standalone.catalog.universal_searches", served
    )
