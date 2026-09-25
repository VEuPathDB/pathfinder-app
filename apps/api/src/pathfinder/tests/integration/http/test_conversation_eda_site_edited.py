"""The conversation route over an analysis the site's own EDA app edited."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.tests._support.eda_wire import AnalysisStore
from pathfinder.tests.integration.http._conversation_eda import (
    bind_thread,
    site_edited_wired,
    thread,
)

pytestmark = pytest.mark.asyncio

__all__ = ["site_edited_wired", "thread"]


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
    assert body["analysis"]["compute"] == {
        "method": "DESeq",
        "identifierVariable": "Gene",
        "valueVariable": "Antisense Count",
        "comparatorVariable": "temperature_condition",
        "groupA": ["normal"],
        "groupB": ["febrile"],
    }
