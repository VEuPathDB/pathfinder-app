"""The four tools that dumped their whole payload now disclose it.

Each ceiling is the wire form the model reads: the tool's return value,
serialized exactly as a ``ToolReturnPart`` sends it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn, ToolReturnPart

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis, eda_catalog, research
from pathfinder.domain.research.citations import (
    Citation,
    LiteratureFilters,
    LiteratureOutputOptions,
    LiteratureSort,
    LiteratureSource,
)
from pathfinder.integrations.eda.models import (
    EdaPermissionEntry,
    EdaStudyDetail,
    EdaStudyDetailResponse,
)
from pathfinder.services.eda.binding import ConversationAnalysisView
from pathfinder.services.eda.catalog import StudyCard, StudySearch
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.processing import (
    EnrichedPaper,
    LiteratureSearchResponse,
)
from pathfinder.services.research.web_search import (
    SearchDiagnostics,
    WebSearchResponse,
    WebSearchResult,
    WebSearchService,
)
from pathfinder.tests.unit.ai.tools.conftest import lead_run_context

FIXTURES = (
    Path(__file__).resolve().parents[3] / "unit" / "integrations" / "eda" / "fixtures"
)

# These four results were the largest on the wire. Each ceiling is well under
# what the same call sent before it disclosed instead of dumping: 11,201 for
# web_search, 18,259 for literature_search, 4,323 for search_eda_studies and
# 9,595 for the filter sheet. Every ceiling is at the tool's default limit.
WEB_SEARCH_CEILING = 3_500
LITERATURE_SEARCH_CEILING = 5_800
EDA_STUDY_SEARCH_CEILING = 3_000
EDA_FILTER_SHEET_CEILING = 7_000

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"


@pytest.fixture
def studies_ctx() -> RunContext[LeadDeps]:
    return lead_run_context(user_prompt="which studies measure phenotype scores")


def wire_size(returned: ToolReturn[object], tool_name: str) -> int:
    """The bytes the model reads, as the tool return part serializes them."""
    part = ToolReturnPart(tool_name=tool_name, content=returned.return_value)
    return len(part.model_response_str().encode())


_PAGE = (
    "Plasmodium falciparum kinases are studied as drug targets because the "
    "parasite kinome diverges from the human one. This page reviews the "
    "FIKK family, the calcium dependent protein kinases and the cyclin "
    "dependent kinase homologues, and lists the inhibitors reported for "
    "each. It closes with a table of the assays used. " * 6
)
_ABSTRACT = (
    "We profiled the Plasmodium falciparum kinome across the intraerythrocytic "
    "development cycle and identified kinases whose transcripts peak in "
    "schizonts. Knockdown of three of them reduced merozoite invasion. " * 8
)


def _web_response(count: int) -> WebSearchResponse:
    results = [
        WebSearchResult(
            title=f"Plasmodium falciparum protein kinases, review {i}",
            url=f"https://example.org/kinome/review-{i}",
            snippet=_PAGE[:600],
            summary=_PAGE[:600],
        )
        for i in range(count)
    ]
    citations = [
        Citation(
            id=f"web_{i:012d}",
            source="web",
            title=r.title,
            url=r.url,
            snippet=r.snippet,
            accessed_at="2026-09-01T00:00:00+00:00",
        )
        for i, r in enumerate(results)
    ]
    return WebSearchResponse(
        query="plasmodium kinases",
        effective_query="plasmodium kinases",
        search_adjusted=False,
        search_diagnostics=SearchDiagnostics(attempts=1, backend="duckduckgo"),
        results=results,
        citations=citations,
    )


def _literature_response(count: int) -> LiteratureSearchResponse:
    papers = [
        EnrichedPaper(
            title=f"Kinome wide analysis of Plasmodium falciparum, part {i}",
            year=2020 + i % 5,
            doi=f"10.1000/pfk.{i}",
            pmid=f"3{i:07d}",
            url=f"https://doi.org/10.1000/pfk.{i}",
            authors=["Smith J", "Okoro A", "Nakamura T", "Ferreira L", "Diallo M"],
            journal_title="Molecular and Biochemical Parasitology",
            abstract=_ABSTRACT[:500],
            snippet=_ABSTRACT[:500],
            source="europepmc",
            score=0.9 - i / 100,
            score_parts={"title": 0.4, "abstract": 0.3, "journal": 0.2},
        )
        for i in range(count)
    ]
    citations = [
        Citation(
            id=f"lit_{i:012d}",
            source="europepmc",
            title=p.title,
            url=p.url,
            authors=p.authors,
            year=p.year,
            doi=p.doi,
            pmid=p.pmid,
            snippet=p.abstract,
            accessed_at="2026-09-01T00:00:00+00:00",
        )
        for i, p in enumerate(papers)
    ]
    return LiteratureSearchResponse(
        query="plasmodium kinome",
        source="all",
        sort="relevance",
        include_abstract=True,
        abstract_max_chars=500,
        max_authors=5,
        filters=LiteratureFilters(),
        results=papers,
        citations=citations,
    )


_DESCRIPTION = (
    "General Description: Phenotypes of genetically modified rodent malaria "
    "parasites, curated from the published literature by the RMgmDB "
    "consortium. Methodology used: manual curation of mutant phenotypes, "
    "including gene deletion, tagging and complementation experiments across "
    "the full life cycle. " * 4
)


def _study_search(count: int) -> StudySearch:
    return StudySearch(
        cards=[
            StudyCard(
                dataset_id=f"DS_53f554ec{i:02d}",
                study_id=f"STUDY_53f554ec{i:02d}",
                display_name=f"Rodent malaria phenotypes, collection {i}",
                short_display_name=f"RodMalPheno{i}",
                description=_DESCRIPTION[:600],
                source_type="curated",
                relevance=0.9 - i / 100,
                can_subset=True,
                can_export_rows=True,
            )
            for i in range(count)
        ]
    )


async def _phenotype_study(
    _site: str,
    _dataset_id: str,
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    payload = json.loads((FIXTURES / "study_detail_phenotype.json").read_text())
    entry = EdaPermissionEntry.model_validate(
        {
            "studyId": _STUDY,
            "displayName": "Rodent malaria phenotypes",
            "actionAuthorization": {"subsetting": True, "resultsAll": True},
        }
    )
    return entry, EdaStudyDetailResponse.model_validate(payload).study


@pytest.fixture(autouse=True)
def stubbed_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every search answers with a full payload, so the cap is what shrinks it."""

    async def _web(
        _self: WebSearchService,
        query: str,
        limit: int = 5,
        *,
        include_summary: bool = False,
        summary_max_chars: int = 600,
    ) -> WebSearchResponse:
        del query, include_summary, summary_max_chars
        return _web_response(limit)

    async def _literature(
        _self: LiteratureSearchService,
        query: str,
        *,
        source: LiteratureSource = "all",
        limit: int = 5,
        sort: LiteratureSort = "relevance",
        options: LiteratureOutputOptions | None = None,
        filters: LiteratureFilters | None = None,
    ) -> LiteratureSearchResponse:
        del query, source, sort, options, filters
        return _literature_response(limit)

    async def _studies(_site: str, _query: str, limit: int = 5) -> StudySearch:
        return _study_search(limit)

    async def _bound(_ctx: object) -> ConversationAnalysisView:
        return ConversationAnalysisView(
            site_id="plasmodb",
            dataset_id=_DATASET,
            analysis_id="t4fszEJ",
            revision=1,
        )

    monkeypatch.setattr(WebSearchService, "search", _web)
    monkeypatch.setattr(LiteratureSearchService, "search", _literature)
    monkeypatch.setattr(eda_catalog, "search_studies", _studies)
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)


async def test_web_search_stays_under_its_ceiling(
    agent_ctx: RunContext[AgentDeps],
) -> None:
    returned = await research.web_search(agent_ctx, "plasmodium kinases")
    assert wire_size(returned, "web_search") < WEB_SEARCH_CEILING


async def test_web_search_keeps_every_result_reachable_by_url(
    agent_ctx: RunContext[AgentDeps],
) -> None:
    """A capped result is still a result: title and url survive the cap."""
    result = (await research.web_search(agent_ctx, "plasmodium kinases")).return_value
    assert len(result.results) == 5
    assert all(r.url for r in result.results)
    assert len(result.results[0].snippet) > len(result.results[4].snippet)


async def test_literature_search_stays_under_its_ceiling(
    agent_ctx: RunContext[AgentDeps],
) -> None:
    returned = await research.literature_search(agent_ctx, "plasmodium kinome")
    assert wire_size(returned, "literature_search") < LITERATURE_SEARCH_CEILING


async def test_literature_search_names_the_handle_for_the_full_record(
    agent_ctx: RunContext[AgentDeps],
) -> None:
    result = (
        await research.literature_search(agent_ctx, "plasmodium kinome")
    ).return_value
    assert len(result.results) == 8
    assert all(r.doi for r in result.results)
    assert "literature_search" in result.guidance
    assert len(result.results[0].abstract) > len(result.results[7].abstract)


async def test_search_eda_studies_stays_under_its_ceiling(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    returned = await eda_catalog.search_eda_studies(studies_ctx, query="rodent malaria")
    assert wire_size(returned, "search_eda_studies") < EDA_STUDY_SEARCH_CEILING


async def test_search_eda_studies_names_the_handle_for_the_full_study(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    result = (
        await eda_catalog.search_eda_studies(studies_ctx, query="rodent malaria")
    ).return_value
    assert len(result.studies) == 5
    assert all(s.dataset_id for s in result.studies)
    assert "describe_eda_study" in result.guidance


async def test_the_eda_filter_sheet_stays_under_its_ceiling(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    returned = await eda_analysis.set_eda_filters(studies_ctx, dataset_id=_DATASET)
    assert wire_size(returned, "set_eda_filters") < EDA_FILTER_SHEET_CEILING


async def test_the_eda_filter_sheet_keeps_every_filterable_variable(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    """A variable dropped from the sheet is a filter the model cannot write."""

    result = (
        await eda_analysis.set_eda_filters(studies_ctx, dataset_id=_DATASET)
    ).return_value
    assert len(result.decide) == 13
    assert all(entry.example for entry in result.decide)
    truncated = [e for e in result.decide if e.vocabulary_total > len(e.vocabulary)]
    assert truncated
    assert all("preview_eda_subset" in (e.vocabulary_note or "") for e in truncated)
