"""The conversation's bound analysis: bind it, read it fresh, clear it."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
)

from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.tests._support.eda_wire import AnalysisStore
from pathfinder.tests._support.published_studies import published_on
from pathfinder.tests.integration.http._conversation_eda import (
    ANALYSIS,
    DATASET,
    ENTITY,
    SPECIES,
    STUDY,
    bind_thread,
    phenotype_wired,
    thread,
)

pytestmark = pytest.mark.asyncio

__all__ = ["phenotype_wired", "thread"]


async def test_an_unbound_thread_reads_as_no_analysis(
    thread: tuple[httpx.AsyncClient, UUID],
) -> None:
    client, conversation_id = thread
    response = await client.get(f"/api/v1/conversations/{conversation_id}/eda")
    assert response.status_code == 200
    body = response.json()
    assert body == {"analysis": None}


async def test_a_bound_thread_reads_the_analysis_state(
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
    assert analysis["compute"] is None
    assert set(body) == {"analysis"}


async def test_a_read_after_the_site_edits_the_analysis_carries_the_edit(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
) -> None:
    """The site and PathFinder share one document, and every read takes it anew."""
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)
    first = await client.get(f"/api/v1/conversations/{conversation_id}/eda")

    phenotype_wired.detail = phenotype_wired.detail.model_copy(
        update={
            "descriptor": EdaAnalysisDescriptor(
                subset=EdaSubsetDescriptor(
                    descriptor=[
                        EdaStringSetFilter(
                            entity_id=ENTITY,
                            variable_id=SPECIES,
                            string_set=["P. yoelii"],
                        )
                    ]
                )
            )
        }
    )
    second = await client.get(f"/api/v1/conversations/{conversation_id}/eda")

    assert first.json()["analysis"]["filterSummaries"] == [
        "Species is one of P. berghei"
    ]
    assert second.json()["analysis"]["filterSummaries"] == [
        "Species is one of P. yoelii"
    ]
    assert phenotype_wired.patches == 0


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


async def test_patching_an_unbound_thread_is_a_conflict(
    thread: tuple[httpx.AsyncClient, UUID],
) -> None:
    """The thread exists, so the refusal is state, not absence."""
    client, conversation_id = thread
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "export-step", "source": "subset"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EDA_NO_OPEN_ANALYSIS"


@pytest.mark.parametrize(
    "body",
    [
        {"action": "set-filters", "filters": []},
        {"action": "run-compute", "computation": {}},
    ],
    ids=["set-filters", "run-compute"],
)
async def test_an_edit_the_site_makes_is_not_an_action_here(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
    body: dict[str, object],
) -> None:
    """The subset and the compute are edited on the site, never through this route."""
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda", json=body
    )

    assert response.status_code == 422
    assert phenotype_wired.patches == 0


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
    async with published_on("plasmodb", DATASET, organism="Plasmodium berghei ANKA"):
        response = await client.patch(
            f"/api/v1/conversations/{conversation_id}/eda",
            json={"action": "bind", "siteId": "plasmodb", "datasetId": DATASET},
        )
    assert response.status_code == 200
    assert len(phenotype_wired.created) == 1
    body = response.json()
    assert body["analysis"]["datasetId"] == DATASET
    assert body["analysis"]["revision"] == 1
    assert set(body) == {"analysis", "step"}
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    bound = await repo.get(conversation_id=conversation_id)
    assert bound is not None
    assert bound.dataset_id == DATASET
