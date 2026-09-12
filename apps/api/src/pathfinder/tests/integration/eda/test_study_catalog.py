"""The study catalog answers with permission-aware cards."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb_mcp.embeddings import sync_study_index

from pathfinder.services.eda import catalog

FIXTURES = FIXTURE_DIR

pytestmark = pytest.mark.asyncio


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


def _route(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/permissions"):
        return httpx.Response(200, json=_fixture("permissions.json"))
    if request.url.path.endswith("/studies"):
        return httpx.Response(200, json=_fixture("studies_list.json"))
    return httpx.Response(404, json={"status": "not-found"})


@pytest.fixture
async def wired(
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[EdaClient]:
    del patch_app_db_engine, db_cleaner
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(_route)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    token = veupathdb_auth_token_ctx.set("t")
    await sync_study_index(await catalog.list_studies("plasmodb"))
    yield client
    veupathdb_auth_token_ctx.reset(token)


async def test_a_search_returns_cards_ordered_by_relevance(wired: EdaClient) -> None:
    cards = (
        await catalog.search_studies("plasmodb", "RNA-Seq expression", limit=5)
    ).cards
    await wired.close()
    assert cards
    assert len(cards) <= 5
    assert cards == sorted(cards, key=lambda c: -c.relevance)
    assert all(c.dataset_id.startswith(("DS_", "EDAUD_")) for c in cards)


async def test_a_card_carries_the_study_id_from_permissions(wired: EdaClient) -> None:
    """The suffixes agree for most curated studies and not for all of them."""
    cards = (await catalog.search_studies("plasmodb", "sequence reads", limit=20)).cards
    await wired.close()
    by_dataset = {c.dataset_id: c for c in cards}
    assert by_dataset["DS_dd73524c7e"].study_id == "STUDY_bf43a6913c"


async def test_a_card_reports_the_two_permission_axes(wired: EdaClient) -> None:
    """subsetting gates a count; resultsAll gates row output."""
    cards = (await catalog.search_studies("plasmodb", "RNA-Seq", limit=20)).cards
    await wired.close()
    assert any(c.can_subset for c in cards)
    assert all(isinstance(c.can_export_rows, bool) for c in cards)


_SPLIT_AXES = {
    "perDataset": {
        "DS_dd73524c7e": {
            "studyId": "STUDY_bf43a6913c",
            "actionAuthorization": {
                "studyMetadata": True,
                "subsetting": True,
                "visualizations": True,
                "resultsFirstPage": True,
                "resultsAll": False,
            },
        }
    }
}


async def test_a_countable_study_that_refuses_rows_says_so_on_its_card(
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A study can be fully countable and refuse rows with a 403."""
    del patch_app_db_engine, db_cleaner

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/permissions"):
            return httpx.Response(200, json=_SPLIT_AXES)
        return _route(request)

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(route)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        await sync_study_index(await catalog.list_studies("plasmodb"))
        cards = (
            await catalog.search_studies("plasmodb", "sequence reads", limit=5)
        ).cards
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()
    assert [(c.dataset_id, c.can_subset, c.can_export_rows) for c in cards] == [
        ("DS_dd73524c7e", True, False)
    ]


async def test_a_study_absent_from_permissions_is_dropped_from_the_cards(
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A study the account cannot see resolves to nothing, so it is not offered."""
    del patch_app_db_engine, db_cleaner

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/permissions"):
            return httpx.Response(200, json={"perDataset": {}})
        if request.url.path.endswith("/studies"):
            return httpx.Response(200, json=_fixture("studies_list.json"))
        return httpx.Response(404, json={"status": "not-found"})

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(route)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        await sync_study_index(await catalog.list_studies("plasmodb"))
        cards = (await catalog.search_studies("plasmodb", "RNA-Seq", limit=5)).cards
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()
    assert cards == []


async def test_the_catalog_is_fetched_once_per_site(
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    calls: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _route(request)

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(route)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        await catalog.search_studies("plasmodb", "one", limit=3)
        await catalog.search_studies("plasmodb", "two", limit=3)
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()
    assert calls.count("/eda/studies") == 1
    assert calls.count("/eda/permissions") == 1


async def test_browsing_lists_the_permitted_catalog_by_display_name(
    wired: EdaClient,
) -> None:
    """The tab's study picker opens with no query, so an empty one lists them."""
    cards = await catalog.browse_studies("plasmodb", limit=100)
    await wired.close()
    assert cards
    assert [c.display_name for c in cards] == sorted(c.display_name for c in cards)
    assert all(c.relevance == 0.0 for c in cards)
    assert all(c.study_id for c in cards)


async def test_browsing_drops_a_study_with_no_permission_entry(
    wired: EdaClient,
) -> None:
    cards = await catalog.browse_studies("plasmodb", limit=100)
    listed = await catalog.list_studies("plasmodb")
    await wired.close()
    assert len(cards) < len(listed)
    assert "DS_ccab256dfb" not in {c.dataset_id for c in cards}


async def test_browsing_honours_the_limit(wired: EdaClient) -> None:
    cards = await catalog.browse_studies("plasmodb", limit=3)
    await wired.close()
    assert len(cards) == 3
