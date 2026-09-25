"""The study list names the genomics sites that publish each study, else the portal."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from veupathdb.eda import EdaClient
from veupathdb_mcp.embeddings import ExperimentCardRow, embedding_session

from pathfinder.tests._support.experiment_cards import LEISHMANIA_ISOLATES_CARD
from pathfinder.tests.integration.http._eda_routes import api_client, eda_wired

pytestmark = pytest.mark.asyncio

__all__ = ["api_client", "eda_wired"]


@pytest.fixture
async def tritrypdb_holds_the_isolates(
    db_engine: AsyncEngine, patch_app_db_engine: None
) -> AsyncGenerator[None]:
    del patch_app_db_engine
    card = LEISHMANIA_ISOLATES_CARD
    async with embedding_session() as session:
        session.add(
            ExperimentCardRow(
                site_id=card.site_id,
                dataset_id=card.dataset_id,
                card=card.model_dump(mode="json", by_alias=True),
            )
        )
        await session.commit()
    yield
    async with db_engine.begin() as conn:
        await conn.exec_driver_sql("TRUNCATE TABLE experiment_cards")


async def test_the_browsed_list_labels_each_study_with_its_sites(
    api_client: tuple[httpx.AsyncClient, UUID],
    eda_wired: EdaClient,
    tritrypdb_holds_the_isolates: None,
) -> None:
    del eda_wired, tritrypdb_holds_the_isolates
    client, _user_id = api_client

    response = await client.get("/api/v1/eda/studies", params={"siteId": "plasmodb"})

    assert response.status_code == 200
    labels = {row["datasetId"]: row["sites"] for row in response.json()["studies"]}
    assert labels["DS_2184f85560"] == ["tritrypdb"]
    assert labels["DS_dd73524c7e"] == ["portal"]
