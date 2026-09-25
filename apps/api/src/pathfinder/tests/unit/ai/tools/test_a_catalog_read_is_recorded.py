"""A catalog read keeps what it answered: each hit in order, with its score."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import SearchMatch

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    serve_no_other_sites,
)


def _match(name: str, display_name: str, similarity: float | None) -> SearchMatch:
    return SearchMatch(
        name=name,
        display_name=display_name,
        description=f"Find genes by {display_name}",
        record_type="transcript",
        relevance=1.0,
        semantic_similarity=similarity,
    )


@pytest.mark.asyncio
async def test_a_read_keeps_its_hits_with_their_similarity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        catalog,
        "search_for_searches",
        AsyncMock(
            return_value=[
                _match("GenesByExportPred", "<i>Exported</i> Protein", 0.44),
                _match("GenesBySignalP", "Signal Peptide", None),
            ]
        ),
    )
    serve_no_other_sites(monkeypatch)
    state = AgentToolState()

    await search_for_searches(
        agent_run_context(agent_state=state), query="genes with a predicted GPI anchor"
    )

    assert state.catalog_reads == [
        CatalogRead(
            tool_call_id="call_1",
            tool="search_for_searches",
            query="genes with a predicted GPI anchor",
            record_type="transcript",
            hits=[
                CatalogHit(
                    name="GenesByExportPred",
                    display_name="Exported Protein",
                    description="Find genes by Exported Protein",
                    record_type="transcript",
                    similarity=0.44,
                ),
                CatalogHit(
                    name="GenesBySignalP",
                    display_name="Signal Peptide",
                    description="Find genes by Signal Peptide",
                    record_type="transcript",
                ),
                CatalogHit(
                    name="GenesByText",
                    display_name="Gene Text Search",
                    description=(
                        "Search all text fields for genes matching a keyword or phrase."
                    ),
                    record_type="transcript",
                ),
            ],
        )
    ]
