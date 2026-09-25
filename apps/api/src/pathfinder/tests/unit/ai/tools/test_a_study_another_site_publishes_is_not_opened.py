"""The EDA tools list a study another site publishes and refuse to open it here."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis, eda_catalog
from pathfinder.ai.tools.standalone._eda_models import EdaStudySearchResult
from pathfinder.services.eda import binding, study_site
from pathfinder.services.eda.catalog import StudyCard, StudySearch
from pathfinder.services.eda.description import EdaPermissionFacts
from pathfinder.tests._support.eda_doubles import permission_entry, study_of
from pathfinder.tests._support.recorded_vdi import no_own_datasets
from pathfinder.tests._support.tool_returns import returned

pytestmark = pytest.mark.asyncio

_MOSQUITO = "DS_89c1f6f48a"
_SENTENCE = (
    "This study is on VectorBase; its genes are not PlasmoDB genes. Ask on VectorBase."
)


async def test_opening_a_study_vectorbase_publishes_is_refused_with_the_site(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    entry = permission_entry()
    study = study_of([], entity_id="ENT_g")
    opened = AsyncMock(return_value="an_1")
    monkeypatch.setattr(
        eda_analysis,
        "_study",
        AsyncMock(return_value=(EdaPermissionFacts.model_validate(entry), study)),
    )
    monkeypatch.setattr(
        binding, "get_study_detail_for_dataset", AsyncMock(return_value=(entry, study))
    )
    monkeypatch.setattr(
        study_site,
        "sites_publishing",
        AsyncMock(return_value={_MOSQUITO: ["vectorbase"]}),
    )
    monkeypatch.setattr(binding, "open_analysis", opened)

    with pytest.raises(ModelRetry) as refused:
        await eda_analysis.open_eda_analysis(
            lead_ctx, dataset_id=_MOSQUITO, purpose="blood meal"
        )

    assert str(refused.value).startswith(_SENTENCE)
    assert lead_ctx.deps.state.domain.open_eda_analysis is None
    opened.assert_not_awaited()


async def test_the_search_lists_a_study_another_site_publishes_as_not_openable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def found(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(
            cards=[
                StudyCard(
                    dataset_id=_MOSQUITO,
                    study_id="STUDY_89c1f6f48a",
                    display_name="Antennal expression following a blood meal",
                    short_display_name="",
                    description="",
                    source_type="curated",
                    relevance=0.61,
                    sites=["vectorbase"],
                    not_here=_SENTENCE,
                )
            ],
            catalog_size=747,
        )

    monkeypatch.setattr(eda_catalog, "search_studies", found)
    monkeypatch.setattr(eda_catalog, "own_dataset_cards", no_own_datasets)

    result = returned(
        await eda_catalog.search_eda_studies(lead_ctx, query="blood meal mosquito"),
        EdaStudySearchResult,
    )

    assert [(s.dataset_id, s.sites, s.not_here) for s in result.studies] == [
        (_MOSQUITO, ["vectorbase"], _SENTENCE)
    ]
    assert (
        "A study with notHere is published on another site and cannot be opened "
        "here" in result.guidance
    )


async def test_the_search_adds_no_site_note_when_every_study_opens_here(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def found(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(
            cards=[
                StudyCard(
                    dataset_id="DS_e973eadd57",
                    study_id="STUDY_e973eadd57",
                    display_name="Heat shock response in sensitive mutants",
                    short_display_name="",
                    description="",
                    source_type="curated",
                    relevance=0.72,
                    sites=["plasmodb"],
                )
            ],
            catalog_size=747,
        )

    monkeypatch.setattr(eda_catalog, "search_studies", found)
    monkeypatch.setattr(eda_catalog, "own_dataset_cards", no_own_datasets)

    result = returned(
        await eda_catalog.search_eda_studies(lead_ctx, query="heat shock"),
        EdaStudySearchResult,
    )

    assert "notHere" not in result.guidance
