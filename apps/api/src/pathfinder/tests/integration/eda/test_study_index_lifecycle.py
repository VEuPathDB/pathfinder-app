"""Who syncs the study index, and what a search answers before it is built."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator

import httpx
import pytest
from assistant_core.embeddings.embedder import EmbeddingUnavailableError

from pathfinder.integrations.eda.models import EdaPermissionEntry, EdaStudyOverview
from pathfinder.integrations.embeddings.study_index import sync_study_index
from pathfinder.platform.config import get_settings
from pathfinder.platform.context import veupathdb_auth_token_ctx
from pathfinder.services.eda import catalog
from pathfinder.services.eda.catalog import (
    NAME_MATCH_GUIDANCE,
    preload_study_index,
    search_studies,
)

_PERMISSIONS = {
    "DS_heat": {
        "studyId": "STUDY_heat",
        "actionAuthorization": {
            "studyMetadata": True,
            "subsetting": True,
            "visualizations": True,
            "resultsFirstPage": True,
            "resultsAll": True,
        },
    },
    "DS_pheno": {
        "studyId": "STUDY_pheno",
        "actionAuthorization": {
            "studyMetadata": True,
            "subsetting": True,
            "visualizations": True,
            "resultsFirstPage": True,
            "resultsAll": True,
        },
    },
}


def _studies() -> list[EdaStudyOverview]:
    return [
        EdaStudyOverview(
            id="STUDY_heat",
            dataset_id="DS_heat",
            sha1hash="h",
            source_type="curated",
            display_name="Heat shock response in sensitive mutants",
            description="febrile temperature RNA-Seq",
        ),
        EdaStudyOverview(
            id="STUDY_pheno",
            dataset_id="DS_pheno",
            sha1hash="h",
            source_type="curated",
            display_name="Rodent malaria phenotype survey",
            description="gene modification success by species",
        ),
    ]


_UNREACHABLE = httpx.ConnectError("the eda service is unreachable")


class _Client:
    """The EDA reads a study search makes, counted."""

    def __init__(self) -> None:
        self.list_calls = 0

    async def list_studies(self) -> list[EdaStudyOverview]:
        self.list_calls += 1
        return _studies()

    async def get_permissions(self) -> dict[str, object]:
        return {
            dataset_id: EdaPermissionEntry.model_validate(entry)
            for dataset_id, entry in _PERMISSIONS.items()
        }


@pytest.fixture
async def wired(
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
    db_cleaner: None,
    embedding_index_cleaner: None,
) -> AsyncGenerator[_Client]:
    del patch_app_db_engine, db_cleaner, embedding_index_cleaner
    client = _Client()
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    token = veupathdb_auth_token_ctx.set("t")
    yield client
    veupathdb_auth_token_ctx.reset(token)


@pytest.fixture
def sync_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("EMBEDDING_INDEX_SYNC_ENABLED", "true")
    monkeypatch.setenv("VEUPATHDB_AUTH_TOKEN", "service-account-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sync_disabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("EMBEDDING_INDEX_SYNC_ENABLED", "false")
    monkeypatch.setenv("VEUPATHDB_AUTH_TOKEN", "service-account-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_a_search_over_an_unbuilt_index_matches_names_and_says_so(
    wired: _Client,
) -> None:
    del wired
    found = await search_studies("plasmodb", "heat shock")
    assert found.guidance == NAME_MATCH_GUIDANCE
    assert [card.dataset_id for card in found.cards] == ["DS_heat"]


async def test_a_search_over_a_built_index_carries_no_name_match_guidance(
    wired: _Client,
) -> None:
    await sync_study_index(await catalog.list_studies("plasmodb"))
    del wired
    found = await search_studies("plasmodb", "heat shock")
    assert found.guidance == ""
    assert {card.dataset_id for card in found.cards} == {"DS_heat", "DS_pheno"}
    assert all(0.0 <= card.relevance <= 1.0 for card in found.cards)
    assert any(card.relevance > 0.0 for card in found.cards)


async def test_an_unreachable_embedding_api_falls_back_to_names(
    wired: _Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await sync_study_index(await catalog.list_studies("plasmodb"))
    del wired

    async def _refuse(query: str, top_k: int) -> list[object]:
        del query, top_k
        raise EmbeddingUnavailableError(batch_size=1, cause="no route to host")

    monkeypatch.setattr(catalog, "search_study_index", _refuse)
    found = await search_studies("plasmodb", "heat shock")
    assert found.guidance == NAME_MATCH_GUIDANCE
    assert [card.dataset_id for card in found.cards] == ["DS_heat"]


async def test_the_warm_up_syncs_the_index_once(
    sync_enabled: None,
    wired: _Client,
) -> None:
    del sync_enabled
    await preload_study_index()
    assert wired.list_calls == 1
    found = await search_studies("plasmodb", "phenotype")
    assert found.guidance == ""


async def test_a_process_that_may_not_sync_reads_nothing(
    sync_disabled: None,
    wired: _Client,
) -> None:
    del sync_disabled
    await preload_study_index()
    assert wired.list_calls == 0


async def test_an_unreachable_eda_service_does_not_raise(
    sync_enabled: None,
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
    db_cleaner: None,
    embedding_index_cleaner: None,
) -> None:
    del sync_enabled, patch_app_db_engine, db_cleaner, embedding_index_cleaner

    class _Failing:
        async def list_studies(self) -> list[EdaStudyOverview]:
            raise _UNREACHABLE

    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: _Failing())
    await preload_study_index()
