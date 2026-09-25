"""The study search answer labels each study with the sites that publish it."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_catalog
from pathfinder.ai.tools.standalone._eda_models import EdaStudySearchResult
from pathfinder.services.eda.catalog import StudyCard, StudySearch
from pathfinder.tests._support.recorded_vdi import no_own_datasets
from pathfinder.tests._support.tool_returns import returned


def _card(dataset_id: str, name: str, sites: list[str]) -> StudyCard:
    return StudyCard(
        dataset_id=dataset_id,
        study_id=f"STUDY_{dataset_id}",
        display_name=name,
        short_display_name="",
        description="",
        source_type="curated",
        relevance=0.6,
        sites=sites,
    )


@pytest.mark.asyncio
async def test_each_study_carries_its_sites(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def found(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(
            cards=[
                _card(
                    "DS_dd73524c7e",
                    "SNP calls of WGS of Parastagonospora nodorum isolates",
                    ["fungidb"],
                ),
                _card("EDAUD_Y9I5UEJtdp0JU", "T. gondii genotyping", ["portal"]),
            ],
            catalog_size=5,
        )

    monkeypatch.setattr(eda_catalog, "search_studies", found)
    monkeypatch.setattr(eda_catalog, "own_dataset_cards", no_own_datasets)

    result = returned(
        await eda_catalog.search_eda_studies(lead_ctx, query="nodorum SNPs"),
        EdaStudySearchResult,
    )

    assert [(s.dataset_id, s.sites) for s in result.studies] == [
        ("DS_dd73524c7e", ["fungidb"]),
        ("EDAUD_Y9I5UEJtdp0JU", ["portal"]),
    ]
