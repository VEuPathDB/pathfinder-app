"""The shared study cache and the shared index hold curated studies only.

``/eda/studies`` answers per account, so a researcher's own study in a
process-wide map would reach every account's browse and the shared index.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient, EdaStudyOverview
from veupathdb.testing import HERMETIC_GUEST_TOKEN
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb_mcp.embeddings import SyncReport

from pathfinder.platform.config import get_settings
from pathfinder.services.eda import catalog
from pathfinder.tests._support.qa_recording import qa_recording


def _listing() -> Any:
    return json.loads(qa_recording(FIXTURE_DIR / "studies_list.json").read_text())


class _Studies:
    """The recorded ``/studies`` answer: curated rows and other accounts' uploads."""

    def __init__(self, body: Any) -> None:
        self.body = body
        self.requests: list[httpx.Request] = []
        self.client = EdaClient(
            base_url="https://qa.plasmodb.org/eda",
            transport=httpx.MockTransport(self._answer),
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self.body)


@pytest.fixture
def studies(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Studies]:
    recorded = _Studies(_listing())
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: recorded.client)
    catalog._studies.clear()
    yield recorded
    catalog._studies.clear()


@pytest.fixture
def sync_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("EMBEDDING_INDEX_SYNC_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("researcher.token")
    yield
    veupathdb_auth_token_ctx.reset(handle)


async def test_the_cache_keeps_the_curated_rows_of_a_listing(
    studies: _Studies,
) -> None:
    del studies
    recorded = _listing()["studies"]
    curated = [row["datasetId"] for row in recorded if row["sourceType"] == "curated"]

    listed = await catalog.list_studies("plasmodb")

    assert [study.dataset_id for study in listed] == curated
    assert len(curated) == 40
    assert len(recorded) == 45


async def test_the_index_is_synced_from_curated_rows_only(
    studies: _Studies, sync_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del studies, sync_enabled
    synced: list[str] = []

    async def _sync(overviews: Sequence[EdaStudyOverview]) -> SyncReport:
        synced.extend(overview.source_type for overview in overviews)
        return SyncReport(added=len(synced))

    monkeypatch.setattr(catalog, "sync_study_index", _sync)

    await catalog.preload_study_index()

    assert synced == ["curated"] * 40


async def test_the_sync_reads_the_listing_as_the_guest_not_the_researcher(
    sync_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del sync_enabled
    studies = _Studies(
        {
            "studies": [
                {
                    "id": f"STUDY_{source_type}",
                    "datasetId": f"DS_{source_type}",
                    "sourceType": source_type,
                    "displayName": source_type,
                }
                for source_type in ("curated", "user_submitted")
            ]
        }
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: studies.client)

    async def _sync(overviews: Sequence[EdaStudyOverview]) -> SyncReport:
        return SyncReport(added=len(overviews))

    monkeypatch.setattr(catalog, "sync_study_index", _sync)

    report = await catalog.preload_study_index()

    assert report == SyncReport(added=1)
    assert [request.headers["cookie"] for request in studies.requests] == [
        f"Authorization={HERMETIC_GUEST_TOKEN}"
    ]
    assert veupathdb_auth_token_ctx.get() == "researcher.token"
