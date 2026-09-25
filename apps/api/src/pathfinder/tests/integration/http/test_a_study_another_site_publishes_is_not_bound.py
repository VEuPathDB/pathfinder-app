"""The tab's bind refuses a study another site publishes, and writes nothing."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.tests._support.eda_wire import AnalysisStore
from pathfinder.tests._support.published_studies import published_on
from pathfinder.tests.integration.http._conversation_eda import (
    DATASET,
    phenotype_wired,
    thread,
)

pytestmark = pytest.mark.asyncio

__all__ = ["phenotype_wired", "thread"]

_BIND = {"action": "bind", "siteId": "plasmodb", "datasetId": DATASET}


async def test_a_study_vectorbase_publishes_is_refused_with_the_site(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
) -> None:
    client, conversation_id = thread

    async with published_on("vectorbase", DATASET, organism="Anopheles gambiae PEST"):
        response = await client.patch(
            f"/api/v1/conversations/{conversation_id}/eda", json=_BIND
        )

    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert problem["detail"] == (
        "This study is on VectorBase; its genes are not PlasmoDB genes. "
        "Ask on VectorBase."
    )
    assert phenotype_wired.created == []
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    assert await repo.get(conversation_id=conversation_id) is None


async def test_a_study_no_genomics_site_publishes_is_refused_naming_the_portal(
    thread: tuple[httpx.AsyncClient, UUID],
    phenotype_wired: AnalysisStore,
) -> None:
    client, conversation_id = thread

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda", json=_BIND
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "This study is on the VEuPathDB Portal; its genes are not PlasmoDB "
        "genes. Ask on the VEuPathDB Portal."
    )
    assert phenotype_wired.created == []


async def test_a_study_the_site_publishes_is_bound(
    thread: tuple[httpx.AsyncClient, UUID],
    phenotype_wired: AnalysisStore,
) -> None:
    client, conversation_id = thread

    async with published_on("plasmodb", DATASET, organism="Plasmodium berghei ANKA"):
        response = await client.patch(
            f"/api/v1/conversations/{conversation_id}/eda", json=_BIND
        )

    assert response.status_code == 200
    assert response.json()["analysis"]["datasetId"] == DATASET
    assert len(phenotype_wired.created) == 1
