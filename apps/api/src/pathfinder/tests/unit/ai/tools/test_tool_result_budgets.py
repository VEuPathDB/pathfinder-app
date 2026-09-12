"""The two EDA tools that dumped their whole payload now disclose it.

Each ceiling is the wire form the model reads: the tool's return value,
serialized exactly as a ``ToolReturnPart`` sends it.
"""

from __future__ import annotations

import json

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn, ToolReturnPart
from veupathdb.eda import (
    EdaPermissionEntry,
    EdaStudyDetail,
    EdaStudyDetailResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis, eda_catalog
from pathfinder.ai.tools.standalone._eda_models import (
    EdaFiltersResult,
    EdaStudySearchResult,
)
from pathfinder.services.eda.binding import ConversationAnalysisView
from pathfinder.services.eda.catalog import StudyCard, StudySearch
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

FIXTURES = FIXTURE_DIR

# These results were the largest on the wire. Each ceiling is well under what
# the same call sent before it disclosed instead of dumping: 4,323 for
# search_eda_studies and 9,595 for the filter sheet. The sheet itself is pinned
# in the instructions now, so its ceiling is the elision floor: a return at or
# under it is never cut from the history.
EDA_STUDY_SEARCH_CEILING = 3_000
EDA_FILTER_SHEET_CEILING = 400

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"


@pytest.fixture
def studies_ctx() -> RunContext[LeadDeps]:
    return lead_run_context(user_prompt="which studies measure phenotype scores")


def wire_size[T](answer: ToolReturn[T], tool_name: str) -> int:
    """The bytes the model reads, as the tool return part serializes them."""
    part = ToolReturnPart(tool_name=tool_name, content=answer.return_value)
    return len(part.model_response_str().encode())


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
        ],
        catalog_size=count,
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
    """Every read answers with a full payload, so the cap is what shrinks it."""

    async def _studies(_site: str, _query: str, limit: int = 5) -> StudySearch:
        return _study_search(limit)

    async def _bound(_ctx: object) -> ConversationAnalysisView:
        return ConversationAnalysisView(
            site_id="plasmodb",
            dataset_id=_DATASET,
            analysis_id="t4fszEJ",
            revision=1,
        )

    monkeypatch.setattr(eda_catalog, "search_studies", _studies)
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)


async def test_search_eda_studies_stays_under_its_ceiling(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    answer = await eda_catalog.search_eda_studies(studies_ctx, query="rodent malaria")
    assert wire_size(answer, "search_eda_studies") < EDA_STUDY_SEARCH_CEILING


async def test_search_eda_studies_names_the_handle_for_the_full_study(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    result = returned(
        await eda_catalog.search_eda_studies(studies_ctx, query="rodent malaria"),
        EdaStudySearchResult,
    )
    assert len(result.studies) == 5
    assert all(s.dataset_id for s in result.studies)
    assert "describe_eda_study" in result.guidance


async def test_the_eda_filter_sheet_stays_under_its_ceiling(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    answer = await eda_analysis.set_eda_filters(studies_ctx, dataset_id=_DATASET)
    assert wire_size(answer, "set_eda_filters") < EDA_FILTER_SHEET_CEILING


async def test_the_eda_filter_sheet_keeps_every_filterable_variable(
    studies_ctx: RunContext[LeadDeps],
) -> None:
    """A variable dropped from the sheet is a filter the model cannot write."""

    result = returned(
        await eda_analysis.set_eda_filters(studies_ctx, dataset_id=_DATASET),
        EdaFiltersResult,
    )
    assert result.sheet_pinned is True
    sheet = studies_ctx.deps.state.domain.open_eda_sheet
    assert sheet is not None
    assert sheet.dataset_id == _DATASET
    pinned = sheet.entries
    assert len(pinned) == 13
    assert all(entry.example for entry in pinned)
    truncated = [e for e in pinned if e.vocabulary_total > len(e.vocabulary)]
    assert truncated
    assert all("preview_eda_subset" in (e.vocabulary_note or "") for e in truncated)
