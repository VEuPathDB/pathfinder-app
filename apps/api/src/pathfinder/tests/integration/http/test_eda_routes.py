"""The EDA catalog routes the tab's study picker reads, and the chart kinds."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.eda import EdaClient
from veupathdb_mcp.embeddings import search_study_index

from pathfinder.tests.integration.http._eda_routes import (
    DATASET,
    api_client,
    eda_wired,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user

pytestmark = pytest.mark.asyncio

__all__ = ["api_client", "eda_wired"]


# The curated studies of the recorded listing that the permissions map names.
_PERMITTED_CURATED = {"DS_dd73524c7e", "DS_2184f85560"}


async def test_a_study_search_answers_with_cards_in_the_indexs_order(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The cache holds curated rows only, so the cards are the two curated
    studies the account may read, ranked as the index ranks them."""
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        "/api/v1/eda/studies", params={"q": "phenotype", "siteId": "plasmodb"}
    )
    hits = [
        hit
        for hit in await search_study_index("phenotype", top_k=100)
        if hit.entry_id in _PERMITTED_CURATED
    ]

    assert response.status_code == 200
    studies = response.json()["studies"]
    assert [(s["datasetId"], s["relevance"]) for s in studies] == [
        (hit.entry_id, pytest.approx(max(0.0, hit.similarity))) for hit in hits
    ]
    assert [s["sourceType"] for s in studies] == ["curated", "curated"]


async def test_a_study_search_with_no_query_lists_the_catalog_by_name(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get("/api/v1/eda/studies", params={"siteId": "plasmodb"})
    assert response.status_code == 200
    studies = response.json()["studies"]
    assert [(s["datasetId"], s["relevance"]) for s in studies] == [
        ("DS_2184f85560", 0.0),
        ("DS_dd73524c7e", 0.0),
    ]
    names = [study["displayName"] for study in studies]
    assert names == sorted(names)


async def test_a_request_with_no_wdk_token_is_refused(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> None:
    """EDA refuses a guest, so a request naming no registered login is a 401."""
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        user = await make_user(session)
    async with client_for(app, user.id) as client:
        response = await client.get(
            "/api/v1/eda/studies", params={"siteId": "plasmodb"}
        )
    assert response.status_code == 401
    assert response.json()["code"] == "WDK_LOGIN_REQUIRED"


async def test_a_missing_site_id_is_a_422(
    api_client: tuple[httpx.AsyncClient, UUID],
) -> None:
    client, _user_id = api_client
    response = await client.get("/api/v1/eda/studies")
    assert response.status_code == 422


async def test_a_chart_kind_outside_the_union_is_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(uuid4())},
        json={"datasetId": DATASET, "chart": "pie"},
    )
    assert response.status_code == 422
