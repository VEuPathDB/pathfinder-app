from __future__ import annotations

import pytest
from assistant_core.platform.types import JSONObject
from veupathdb_mcp.catalog import SearchMatch

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    serve_no_other_sites,
)
from pathfinder.tests.unit.ai.tools.test_catalog import _match, _serve


async def test_the_sites_term_pair_searches_follow_the_ranked_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_no_other_sites(monkeypatch)
    _serve(monkeypatch, "search_for_searches", [_match("GenesByTaxon", "Taxon", 0.8)])
    asked: list[tuple[str, str | list[str] | None]] = []

    async def served(
        site_id: str, record_type: str | list[str] | None
    ) -> tuple[SearchMatch, ...]:
        asked.append((site_id, record_type))
        return (
            _match("GenesByText", "Text", 0.0),
            _match("GenesByInterproDomain", "InterPro Domain", 0.0),
        )

    monkeypatch.setattr(
        "pathfinder.ai.tools.standalone.catalog.universal_searches", served
    )

    result = returned(
        await search_for_searches(
            agent_run_context(agent_state=AgentToolState()),
            query="kinase genes",
            record_type="transcript",
        ),
        list[JSONObject],
    )

    assert [row.get("name") for row in result] == [
        "GenesByTaxon",
        "GenesByText",
        "GenesByInterproDomain",
    ]
    assert asked == [("plasmodb", "transcript")]
