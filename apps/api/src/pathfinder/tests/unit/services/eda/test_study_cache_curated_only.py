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
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb_mcp.embeddings import SyncReport

from pathfinder.platform.config import get_settings
from pathfinder.services.eda import catalog


def _listing() -> Any:
    return json.loads((FIXTURE_DIR / "studies_list.json").read_text())


@pytest.fixture
def studies(monkeypatch: pytest.MonkeyPatch) -> Iterator[EdaClient]:
    """The recorded ``/studies`` answer: curated rows and other accounts' uploads."""
    client = EdaClient(
        base_url="https://plasmodb.org/eda",
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=_listing())),
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    catalog._studies.clear()
    yield client
    catalog._studies.clear()


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("researcher.token")
    yield
    veupathdb_auth_token_ctx.reset(handle)


async def test_the_cache_keeps_the_curated_rows_of_a_listing(
    studies: EdaClient,
) -> None:
    del studies
    recorded = _listing()["studies"]
    curated = [row["datasetId"] for row in recorded if row["sourceType"] == "curated"]

    listed = await catalog.list_studies("plasmodb")

    assert [study.dataset_id for study in listed] == curated
    assert len(curated) == 40
    assert len(recorded) == 52


async def test_the_index_is_synced_from_curated_rows_only(
    studies: EdaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    del studies
    synced: list[str] = []

    async def _sync(overviews: Sequence[EdaStudyOverview]) -> SyncReport:
        synced.extend(overview.source_type for overview in overviews)
        return SyncReport(added=len(synced))

    monkeypatch.setattr(catalog, "sync_study_index", _sync)
    monkeypatch.setenv("EMBEDDING_INDEX_SYNC_ENABLED", "true")
    monkeypatch.setenv("VEUPATHDB_AUTH_TOKEN", "service.account.token")
    get_settings.cache_clear()
    try:
        await catalog.preload_study_index()
    finally:
        get_settings.cache_clear()

    assert synced == ["curated"] * 40
