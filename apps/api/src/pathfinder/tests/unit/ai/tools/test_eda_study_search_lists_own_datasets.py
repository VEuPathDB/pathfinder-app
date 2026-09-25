"""The study search puts the researcher's installed uploads ahead of the site's ranking."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic_ai import RunContext
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_catalog
from pathfinder.ai.tools.standalone._eda_models import EdaStudySearchResult
from pathfinder.services.eda import catalog, private_datasets
from pathfinder.services.eda.catalog import StudyCard, StudySearch
from pathfinder.tests._support.recorded_vdi import (
    RecordedPermissions,
    RecordedVdi,
    installed_user_study,
    permissions_body,
    vdi_body,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import summary_of

# The newer upload first, as the owned listing orders them.
_OWN = ("ctZ5MhpEs50I5", "4xZ5Q5pV1s4IM")
_RANKED = [f"DS_ranked{rank}" for rank in range(5)]


def _card(dataset_id: str) -> StudyCard:
    return StudyCard(
        dataset_id=dataset_id,
        study_id=f"STUDY_{dataset_id}",
        display_name=f"Study {dataset_id}",
        short_display_name="",
        description="",
        source_type="curated",
        relevance=0.5,
        sites=["plasmodb"],
    )


async def _ranked(_site: str, _query: str, limit: int = 5) -> StudySearch:
    del limit
    return StudySearch(
        cards=[_card(dataset_id) for dataset_id in _RANKED], catalog_size=40
    )


@pytest.fixture(autouse=True)
def _researcher() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("researcher.token")
    yield
    veupathdb_auth_token_ctx.reset(handle)


def _serve_two_installed_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = [row for row in vdi_body("datasets_owned") if row["datasetId"] in _OWN]
    permissions = permissions_body(with_user_study=True)
    _dataset_id, entry = installed_user_study()
    permissions["perDataset"][f"EDAUD_{_OWN[0]}"] = entry
    served = RecordedPermissions([permissions])
    vdi = RecordedVdi(listing=listing)
    monkeypatch.setattr(private_datasets, "get_vdi_client", lambda _s: vdi.client())
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: served.client())
    monkeypatch.setattr(eda_catalog, "search_studies", _ranked)


@pytest.mark.asyncio
async def test_the_researchers_uploads_come_first_and_the_ranking_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_two_installed_uploads(monkeypatch)

    answer = await eda_catalog.search_eda_studies(
        lead_run_context(tool_call_id="call_1"), query="heat shock"
    )
    result = returned(answer, EdaStudySearchResult)

    assert summary_of(answer).data["summary"] == (
        "2 of your own studies, 5 closest of 40 studies on this site (best match 0.50)"
    )
    assert [
        (study.dataset_id, study.source_type, study.sites) for study in result.studies
    ] == [
        (f"EDAUD_{_OWN[0]}", "user_submitted", ["plasmodb"]),
        (f"EDAUD_{_OWN[1]}", "user_submitted", ["plasmodb"]),
        *[(dataset_id, "curated", ["plasmodb"]) for dataset_id in _RANKED],
    ]
    assert result.guidance.endswith(
        "Studies marked user_submitted are this researcher's own uploads."
    )


@pytest.mark.asyncio
async def test_an_upload_whose_name_matches_comes_before_one_that_does_not(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _serve_two_installed_uploads(monkeypatch)

    result = returned(
        await eda_catalog.search_eda_studies(lead_ctx, query="stranded"),
        EdaStudySearchResult,
    )

    assert [study.dataset_id for study in result.studies[:2]] == [
        f"EDAUD_{_OWN[1]}",
        f"EDAUD_{_OWN[0]}",
    ]


@pytest.mark.asyncio
async def test_the_researchers_uploads_answer_when_the_site_ranks_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _nothing(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(cards=[], catalog_size=40)

    _serve_two_installed_uploads(monkeypatch)
    monkeypatch.setattr(eda_catalog, "search_studies", _nothing)

    answer = await eda_catalog.search_eda_studies(
        lead_run_context(tool_call_id="call_1"), query="heat shock"
    )

    result = returned(answer, EdaStudySearchResult)
    assert [study.dataset_id for study in result.studies] == [
        f"EDAUD_{_OWN[0]}",
        f"EDAUD_{_OWN[1]}",
    ]
    assert summary_of(answer).data["summary"] == "2 of your own studies"
