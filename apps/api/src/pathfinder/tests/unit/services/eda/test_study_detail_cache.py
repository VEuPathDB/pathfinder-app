"""A cached curated study detail is addressed by the content hash its listing reports."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient, EdaStudyOverview

from pathfinder.services.eda import catalog

pytestmark = pytest.mark.asyncio

_DETAIL = {"study": {"id": "STUDY_a", "rootEntity": {"id": "ENT_1"}}}


def _overview(*, sha: str, modified: str) -> EdaStudyOverview:
    return EdaStudyOverview(
        id="STUDY_a",
        dataset_id="DS_a",
        sha1hash=sha,
        source_type="curated",
        display_name="Alpha",
        last_modified=modified,
    )


@pytest.fixture(autouse=True)
def _token() -> Generator[None]:
    token = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(token)


@pytest.fixture
async def detail_calls(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=_DETAIL)

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    yield calls
    await client.close()


async def test_one_study_is_fetched_once(detail_calls: list[str]) -> None:
    study = _overview(sha="h1", modified="2026-05-27T20:00:00-04:00")
    first = await catalog.get_study_detail("plasmodb", study)
    second = await catalog.get_study_detail("plasmodb", study)
    assert first.root_entity.id == "ENT_1"
    assert second is first
    assert detail_calls == ["/eda/studies/STUDY_a"]


async def test_a_new_sha1hash_refetches_the_detail(detail_calls: list[str]) -> None:
    """A curated study keys on its content hash, so new content is a new read."""
    await catalog.get_study_detail(
        "plasmodb", _overview(sha="h1", modified="2026-05-27T20:00:00-04:00")
    )
    await catalog.get_study_detail(
        "plasmodb", _overview(sha="h2", modified="2026-05-27T20:00:00-04:00")
    )
    assert detail_calls == ["/eda/studies/STUDY_a", "/eda/studies/STUDY_a"]
