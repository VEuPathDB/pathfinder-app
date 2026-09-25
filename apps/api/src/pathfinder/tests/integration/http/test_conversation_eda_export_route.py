"""The conversation's export and unbind actions over the EDA route."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.eda_wire import AnalysisStore
from pathfinder.tests.integration.http._conversation_eda import (
    bind_thread,
    hermetic_wdk,
    phenotype_wired,
    site_edited_wired,
    thread,
)
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

pytestmark = pytest.mark.asyncio

__all__ = ["hermetic_wdk", "phenotype_wired", "site_edited_wired", "thread"]


async def test_a_volcano_export_writes_the_cut_the_analysis_stores(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    site_edited_wired: AnalysisStore,
    hermetic_wdk: None,
) -> None:
    """The site's stored cut rides in the step's analysis spec."""
    del site_edited_wired, hermetic_wdk
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "export-step", "source": "volcano"},
    )
    assert response.status_code == 200
    body = response.json()
    exported = next(
        step for step in body["step"]["steps"] if step["searchName"] == COMPUTE_QUERY
    )
    spec = json.loads(exported["parameters"]["eda_analysis_spec"]["value"])
    volcano = spec["descriptor"]["computations"][0]["visualizations"][0]
    assert volcano["descriptor"]["configuration"] == {
        "effectSizeThreshold": 1.0,
        "significanceThreshold": 0.05,
        "effectDirection": "upAndDown",
        "markerBodyOpacity": 0.5,
    }
    assert body["analysis"]["revision"] == 1


async def test_export_step_on_a_thread_with_no_strategy_begins_it(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    phenotype_wired: AnalysisStore,
    hermetic_wdk: None,
) -> None:
    """The tab's first export is the thread's root step, through the real commit."""
    del phenotype_wired, hermetic_wdk
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "export-step", "source": "subset"},
    )
    assert response.status_code == 200
    step = response.json()["step"]
    assert [leaf["searchName"] for leaf in step["steps"]] == [SUBSET_QUERY]
    assert step["rootStepId"] == step["steps"][0]["id"]


async def test_an_action_outside_the_union_is_a_422(
    thread: tuple[httpx.AsyncClient, UUID],
) -> None:
    client, conversation_id = thread
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "rename"},
    )
    assert response.status_code == 422


async def test_a_body_that_names_no_action_is_a_422(
    thread: tuple[httpx.AsyncClient, UUID],
) -> None:
    client, conversation_id = thread
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"filters": []},
    )
    assert response.status_code == 422


async def test_another_users_thread_is_not_readable(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        owner = await make_user(session)
        other = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=owner.id
        )
        session.add(conversation)
        await session.commit()
    async with first_frame_client_for(app, other.id, wdk_token="t") as client:
        read = await client.get(f"/api/v1/conversations/{conversation.id}/eda")
        written = await client.patch(
            f"/api/v1/conversations/{conversation.id}/eda",
            json={"action": "unbind"},
        )
    assert read.status_code == 404
    assert written.status_code == 404
