"""The conversation's bound analysis: read it, mutate its subset, clear it."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.tests._support.eda_wire import AnalysisStore
from pathfinder.tests.integration.http._conversation_eda import (
    ANALYSIS,
    DATASET,
    ENTITY,
    SPECIES,
    STUDY,
    bind_thread,
    empty_subset_wired,
    phenotype_wired,
    thread,
)

pytestmark = pytest.mark.asyncio

__all__ = ["empty_subset_wired", "phenotype_wired", "thread"]


async def test_an_unbound_thread_reads_as_no_analysis(
    thread: tuple[httpx.AsyncClient, UUID],
) -> None:
    client, conversation_id = thread
    response = await client.get(f"/api/v1/conversations/{conversation_id}/eda")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"analysis", "descriptor"}
    assert body["analysis"] is None
    assert body["descriptor"] is None


async def test_a_bound_thread_reads_the_analysis_state_and_the_descriptor(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
) -> None:
    """The tab hydrates from the same snapshot the part and the PATCH carry."""
    del phenotype_wired
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.get(f"/api/v1/conversations/{conversation_id}/eda")
    assert response.status_code == 200
    body = response.json()
    analysis = body["analysis"]
    assert analysis["analysisId"] == ANALYSIS
    assert analysis["datasetId"] == DATASET
    assert analysis["siteId"] == "plasmodb"
    assert analysis["studyId"] == STUDY
    assert analysis["studyDisplayName"]
    assert analysis["displayName"] == "berghei subset"
    assert analysis["numFilters"] == 1
    assert analysis["revision"] == 0
    assert analysis["filterSummaries"] == ["Species is one of P. berghei"]
    assert analysis["filters"][0]["stringSet"] == ["P. berghei"]
    assert analysis["canExportRows"] is True
    assert analysis["entityCounts"] == [
        {
            "entityId": ENTITY,
            "entityDisplayName": "Gene Phenotype Data",
            "count": 4011,
            "unfilteredCount": 4279,
        }
    ]
    assert body["descriptor"]["subset"]["descriptor"][0]["stringSet"] == ["P. berghei"]


async def test_a_read_does_not_count_as_a_mutation(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
) -> None:
    """Hydration is read-only, so two GETs report the same revision."""
    del phenotype_wired
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    first = await client.get(f"/api/v1/conversations/{conversation_id}/eda")
    second = await client.get(f"/api/v1/conversations/{conversation_id}/eda")

    assert first.json()["analysis"]["revision"] == 0
    assert second.json()["analysis"]["revision"] == 0
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    bound = await repo.get(conversation_id=conversation_id)
    assert bound is not None
    assert bound.revision == 0


async def test_patching_the_filters_replaces_the_subset(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
) -> None:
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "set-filters",
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
    assert phenotype_wired.patches == 1
    written = phenotype_wired.detail.descriptor.subset.descriptor
    assert [f.variable_id for f in written] == [SPECIES]
    body = response.json()
    assert set(body) == {"analysis", "job", "step"}
    assert body["analysis"]["numFilters"] == 1
    assert body["analysis"]["revision"] == 1
    assert body["job"] is None
    assert body["step"] is None


async def test_patching_an_unbound_thread_is_a_conflict(
    thread: tuple[httpx.AsyncClient, UUID],
) -> None:
    """The thread exists, so the refusal is state, not absence."""
    client, conversation_id = thread
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "set-filters", "filters": []},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EDA_NO_OPEN_ANALYSIS"


async def test_patching_an_invalid_filter_array_is_a_422_naming_the_value(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    empty_subset_wired: AnalysisStore,
) -> None:
    """A value outside the vocabulary empties the subset, and the tab is told."""
    del empty_subset_wired
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "set-filters",
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


async def test_unbinding_clears_the_binding(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    client, conversation_id = thread
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await bind_thread(session_maker, conversation_id)
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda", json={"action": "unbind"}
    )
    assert response.status_code == 200
    assert response.json()["analysis"] is None
    assert await repo.get(conversation_id=conversation_id) is None


async def test_unbinding_an_unbound_thread_leaves_it_unbound(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Unbind is idempotent; the only 404 in the handler is the ownership check."""
    client, conversation_id = thread
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda", json={"action": "unbind"}
    )
    assert response.status_code == 200
    assert response.json()["analysis"] is None
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    assert await repo.get(conversation_id=conversation_id) is None


async def test_bind_creates_the_upstream_analysis_and_the_row(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
) -> None:
    """Bind writes the analysis document upstream and the row that names it."""
    client, conversation_id = thread
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "bind", "siteId": "plasmodb", "datasetId": DATASET},
    )
    assert response.status_code == 200
    assert len(phenotype_wired.created) == 1
    body = response.json()
    assert body["analysis"]["datasetId"] == DATASET
    assert body["analysis"]["revision"] == 1
    assert body["job"] is None
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    bound = await repo.get(conversation_id=conversation_id)
    assert bound is not None
    assert bound.dataset_id == DATASET
