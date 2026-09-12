"""The EDA catalog routes the tab hydrates its study picker from."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.eda import EdaClient

from pathfinder.tests.integration.http._eda_routes import (
    DATASET,
    ENTITY,
    HIDDEN,
    SPECIES,
    STUDY,
    api_client,
    eda_wired,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user

pytestmark = pytest.mark.asyncio

__all__ = ["api_client", "eda_wired"]


async def test_a_study_search_answers_with_cards(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        "/api/v1/eda/studies", params={"q": "phenotype", "siteId": "plasmodb"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["studies"]
    first = body["studies"][0]
    assert set(first) >= {
        "datasetId",
        "studyId",
        "displayName",
        "canSubset",
        "canExportRows",
        "relevance",
    }
    assert first["relevance"] > 0.0


async def test_a_study_search_with_no_query_lists_the_catalog_by_name(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get("/api/v1/eda/studies", params={"siteId": "plasmodb"})
    assert response.status_code == 200
    studies = response.json()["studies"]
    assert studies
    names = [study["displayName"] for study in studies]
    assert names == sorted(names)
    assert all(study["relevance"] == 0.0 for study in studies)


async def test_a_study_detail_carries_the_entity_tree_and_the_gene_entity(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{DATASET}", params={"siteId": "plasmodb"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["datasetId"] == DATASET
    assert body["studyId"] == STUDY
    assert body["geneEntityId"] == ENTITY
    assert body["canSubset"] is True
    entities = {e["entityId"] for e in body["entities"]}
    assert ENTITY in entities
    variables = body["variables"]
    assert any(v["variableId"] == SPECIES for v in variables)


async def test_a_study_detail_for_one_entity_carries_that_entity_only(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """A study can declare thousands of variables, so the tab asks per entity."""
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{DATASET}",
        params={"siteId": "plasmodb", "entityId": ENTITY},
    )
    assert response.status_code == 200
    variables = response.json()["variables"]
    assert variables
    assert {v["entityId"] for v in variables} == {ENTITY}
    species = next(v for v in variables if v["variableId"] == SPECIES)
    assert species["filterType"] == "stringSet"
    assert "P. berghei" in species["vocabulary"]


async def test_a_study_detail_carries_the_hide_from_advice_of_each_variable(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The tab lists what the site lists, so it needs the site's advice."""
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{DATASET}",
        params={"siteId": "plasmodb", "entityId": ENTITY},
    )
    assert response.status_code == 200
    hide_from = {v["variableId"]: v["hideFrom"] for v in response.json()["variables"]}
    assert hide_from[HIDDEN] == ["variableTree"]
    assert hide_from[SPECIES] == []


async def test_a_study_detail_for_an_unknown_entity_is_a_404(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{DATASET}",
        params={"siteId": "plasmodb", "entityId": "NO_SUCH_ENTITY"},
    )
    assert response.status_code == 404
    assert "NO_SUCH_ENTITY" in json.dumps(response.json())


async def test_an_unknown_dataset_is_a_404_naming_the_id(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        "/api/v1/eda/studies/DS_nope", params={"siteId": "plasmodb"}
    )
    assert response.status_code == 404
    assert "DS_nope" in json.dumps(response.json())


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
