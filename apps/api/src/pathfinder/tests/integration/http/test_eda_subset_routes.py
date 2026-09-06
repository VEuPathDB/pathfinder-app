"""The EDA subsetting routes: a count, a distribution and a chart kind."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from veupathdb.eda.client import EdaClient

from pathfinder.tests.integration.http._eda_routes import (
    DATASET,
    ENTITY,
    SPECIES,
    api_client,
    eda_wired,
)

pytestmark = pytest.mark.asyncio

__all__ = ["api_client", "eda_wired"]


async def test_count_answers_with_the_service_count(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/count",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": DATASET,
            "entityId": ENTITY,
            "filters": [
                {
                    "entityId": ENTITY,
                    "variableId": SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. berghei"],
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entityId"] == ENTITY
    assert body["count"] == 4011
    assert body["unfilteredCount"] == 4279


async def test_count_refuses_an_out_of_vocabulary_value_with_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The service answers 200 with count 0, so the route must refuse first."""
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/count",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": DATASET,
            "entityId": ENTITY,
            "filters": [
                {
                    "entityId": ENTITY,
                    "variableId": SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. vivax"],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "P. vivax" in json.dumps(response.json())


async def test_count_refuses_an_unknown_filter_type_with_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The discriminated union refuses stringPrefixSet before any wire call."""
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/count",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": DATASET,
            "entityId": ENTITY,
            "filters": [
                {
                    "entityId": ENTITY,
                    "variableId": "V",
                    "type": "stringPrefixSet",
                    "prefixSet": ["ab"],
                }
            ],
        },
    )
    assert response.status_code == 422


async def test_distribution_answers_with_labels_and_values_of_equal_length(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/distribution",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": DATASET,
            "entityId": ENTITY,
            "variableId": SPECIES,
            "filters": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["variableId"] == SPECIES
    assert body["variableDisplayName"] == "Species"
    assert len(body["labels"]) == len(body["values"])
    assert body["labels"][0] == "P. berghei"
    assert body["numVarValues"] == 8409
    assert body["isMultiValued"] is True


async def test_distribution_refuses_an_out_of_vocabulary_filter_with_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/distribution",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": DATASET,
            "entityId": ENTITY,
            "variableId": SPECIES,
            "filters": [
                {
                    "entityId": ENTITY,
                    "variableId": SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. vivax"],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "P. vivax" in json.dumps(response.json())


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
