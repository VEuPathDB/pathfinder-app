"""The recorded EDA deployment the route tests hydrate from."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.client import EdaClient
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb_mcp.embeddings.study_index import sync_study_index

from pathfinder.services.eda import authoring, catalog, compute
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

FIXTURES = FIXTURE_DIR

DATASET = "DS_53f554ec6a"
STUDY = "STUDY_53f554ec6a"
ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
SPECIES = "VAR_035294d0"
HIDDEN = "VAR_71b4a7d4"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


_FIXTURE_BY_SUFFIX = {
    "/permissions": "permissions.json",
    "/eda/studies": "studies_list.json",
    f"/eda/studies/{STUDY}": "study_detail_phenotype.json",
    "/distribution": "distribution_categorical.json",
    "/statistics": "volcano_statistics.json",
}


def _body(path: str, counts: list[int]) -> object | None:
    """The recorded response for one EDA path, or None when there is none."""
    for suffix, name in _FIXTURE_BY_SUFFIX.items():
        if path.endswith(suffix):
            return fixture(name)
    if path.endswith("/count"):
        return {"count": counts.pop(0)}
    if "/visualizations/" in path:
        return fixture("volcano_statistics.json")
    return None


def route(counts: list[int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = _body(request.url.path, counts)
        if body is None:
            return httpx.Response(404, json={"status": "not-found"})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


@pytest.fixture
async def eda_wired(
    monkeypatch: pytest.MonkeyPatch,
    patch_app_db_engine: None,
) -> AsyncGenerator[EdaClient]:
    del patch_app_db_engine
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=route([4011, 4279])
    )
    for module in (catalog, authoring, compute):
        monkeypatch.setattr(module, "get_eda_client", lambda _s: client)
    # The api syncs the study index at warm-up; a route only searches it.
    token = veupathdb_auth_token_ctx.set("t")
    await sync_study_index(await catalog.list_studies("plasmodb"))
    veupathdb_auth_token_ctx.reset(token)
    yield client
    await client.close()


@pytest.fixture
async def api_client(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[tuple[httpx.AsyncClient, UUID]]:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        user = await make_user(session)
    client = first_frame_client_for(app, user.id, wdk_token="test-token")
    async with client:
        yield client, user.id
