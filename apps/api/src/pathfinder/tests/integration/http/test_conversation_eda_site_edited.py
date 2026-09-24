"""The conversation routes over an analysis the site's own EDA app edited."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.tests._support.eda_wire import JOB_ID, AnalysisStore, fixture
from pathfinder.tests.integration.http._conversation_eda import (
    ANALYSIS,
    bind_thread,
    computation_json,
    site_edited_wired,
    thread,
)

pytestmark = pytest.mark.asyncio

__all__ = ["site_edited_wired", "thread"]

_RECORDED = fixture("analysis_detail_pass_and_de")


def _recorded(computation_id: str) -> dict[str, Any]:
    computations: list[dict[str, Any]] = _RECORDED["descriptor"]["computations"]
    return next(c for c in computations if c["computationId"] == computation_id)


async def test_the_tab_reads_an_analysis_with_a_pass_compute(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    site_edited_wired: AnalysisStore,
) -> None:
    del site_edited_wired
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.get(f"/api/v1/conversations/{conversation_id}/eda")

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["analysisId"] == "uoZgkI9"
    assert body["analysis"]["numComputations"] == 2
    assert body["analysis"]["entityCounts"] == [
        {
            "entityId": "ENT_8151325d",
            "entityDisplayName": "Sample",
            "count": 12,
            "unfilteredCount": 12,
        },
        {
            "entityId": "ENT_fd574cd6",
            "entityDisplayName": "pfal3D7 htseq counts",
            "count": 68640,
            "unfilteredCount": 68640,
        },
    ]
    computations = body["descriptor"]["computations"]
    assert [c["computationId"] for c in computations] == ["k3x9q", "m7p2d"]
    assert computations[0]["visualizations"][0]["descriptor"]["type"] == "histogram"
    volcano = computations[1]["visualizations"][0]["descriptor"]
    assert volcano["configuration"]["effectSizeThreshold"] == 1
    assert volcano["configuration"]["significanceThreshold"] == 0.05


async def test_a_compute_run_replaces_the_comparison_and_keeps_the_pass(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    site_edited_wired: AnalysisStore,
) -> None:
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": computation_json()},
    )

    assert response.status_code == 200
    assert response.json()["job"]["jobId"] == JOB_ID
    assert response.json()["analysis"]["numComputations"] == 2
    [body] = site_edited_wired.patched
    computations = body["descriptor"]["computations"]
    assert [c["computationId"] for c in computations] == ["k3x9q", ANALYSIS]
    assert computations[0] == _recorded("k3x9q")
    value_variable = computations[1]["descriptor"]["configuration"]["valueVariable"]
    assert value_variable["variableId"] == "SEQUENCE_READ_COUNT_SENSE"
