"""An experiment names a gene set its caller holds, on every route that creates one."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.tests.integration.http.conftest import first_frame_client_for, make_user
from pathfinder.transport.http.routers.experiments._config import config_from_request
from pathfinder.transport.http.schemas.experiments import CreateExperimentRequest

SITE_ID = "plasmodb"
GENE_IDS = ("PF3D7_0100100", "PF3D7_0100200")
ORGANISM = "Plasmodium falciparum 3D7"
CREATE = "/api/v1/experiments"
BATCH = "/api/v1/experiments/batch"
BENCHMARK = "/api/v1/experiments/benchmark"
ROUTES = (CREATE, BATCH, BENCHMARK)


def _create_body(gene_set_id: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "siteId": SITE_ID,
        "recordType": "transcript",
        "searchName": "GenesByText",
        "parameters": {},
        "positiveControls": [GENE_IDS[0]],
        "negativeControls": [GENE_IDS[1]],
        "controlsSearchName": "GeneByLocusTag",
        "controlsParamName": "ds_gene_ids",
        "name": "borrowed evaluation",
    }
    if gene_set_id is not None:
        body["geneSetId"] = gene_set_id
    return body


def _body_for(url: str, gene_set_id: str | None) -> dict[str, Any]:
    base = _create_body(gene_set_id)
    if url == BATCH:
        return {
            "base": base,
            "organismParamName": "organism",
            "targetOrganisms": [{"organism": ORGANISM}],
        }
    if url == BENCHMARK:
        return {
            "base": base,
            "controlSets": [
                {
                    "label": "primary",
                    "positiveControls": [GENE_IDS[0]],
                    "negativeControls": [GENE_IDS[1]],
                    "isPrimary": True,
                },
            ],
        }
    return base


async def _gene_set_held_by(user_id: UUID) -> str:
    gene_set = await GeneSetService(get_gene_set_store()).create(
        user_id=user_id,
        name="held set",
        site_id=SITE_ID,
        gene_ids=list(GENE_IDS),
        source="paste",
    )
    return gene_set.id


@pytest.mark.parametrize("url", ROUTES)
async def test_a_foreign_gene_set_is_refused_and_writes_no_experiment(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    db_session: AsyncSession,
    url: str,
) -> None:
    """The set belongs to somebody else, so the run never starts."""
    owner = await make_user(db_session)
    gene_set_id = await _gene_set_held_by(owner.id)

    response = await authed_client.post(url, json=_body_for(url, gene_set_id))

    assert response.status_code == 404, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["code"] == "NOT_FOUND"
    assert problem["detail"] == f"Gene set not found: {gene_set_id}"

    store = get_experiment_store()
    assert await store.alist_for_gene_set(gene_set_id, authed_user_id) == []
    assert await store.alist_for_gene_set(gene_set_id, owner.id) == []


@pytest.mark.parametrize("url", ROUTES)
async def test_a_gene_set_the_caller_holds_starts_the_run(
    app: FastAPI,
    authed_user_id: UUID,
    signed_in_to_veupathdb: None,
    url: str,
) -> None:
    """The owner reaches the stream, so the refusal above is about ownership."""
    del signed_in_to_veupathdb
    gene_set_id = await _gene_set_held_by(authed_user_id)

    async with first_frame_client_for(app, authed_user_id) as client:
        response = await client.post(url, json=_body_for(url, gene_set_id))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.parametrize("url", ROUTES)
async def test_a_body_that_names_no_gene_set_starts_the_run(
    app: FastAPI,
    authed_user_id: UUID,
    signed_in_to_veupathdb: None,
    url: str,
) -> None:
    """No gene set id means no ownership read and no refusal."""
    del signed_in_to_veupathdb

    async with first_frame_client_for(app, authed_user_id) as client:
        response = await client.post(url, json=_body_for(url, None))

    assert response.status_code == 200, response.text


async def test_the_config_carries_the_gene_set_the_caller_holds(
    authed_user_id: UUID,
) -> None:
    """The verified id reaches the experiment, which is how the set finds it again."""
    gene_set_id = await _gene_set_held_by(authed_user_id)
    request = CreateExperimentRequest.model_validate(_create_body(gene_set_id))

    config = await config_from_request(request, authed_user_id)

    assert config.gene_set_id == gene_set_id
    assert config.search_name == "GenesByText"


async def test_the_config_of_a_body_with_no_gene_set_names_none(
    authed_user_id: UUID,
) -> None:
    request = CreateExperimentRequest.model_validate(_create_body(None))

    config = await config_from_request(request, authed_user_id)

    assert config.gene_set_id is None
    assert config.positive_controls == [GENE_IDS[0]]
