"""The conversation's compute and export actions over the EDA route."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb_mcp.catalog.eda_backed import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.eda_wire import JOB_ID, AnalysisStore
from pathfinder.tests.integration.http._conversation_eda import (
    DATASET,
    bind_thread,
    computation_json,
    de_wired,
    hermetic_wdk,
    phenotype_wired,
    thread,
)
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

pytestmark = pytest.mark.asyncio

__all__ = ["de_wired", "hermetic_wdk", "phenotype_wired", "thread"]


async def test_run_compute_answers_with_the_job_reference(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
) -> None:
    """The tab gets the job the compute service submitted, and the new revision."""
    del de_wired
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": computation_json()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["jobId"] == JOB_ID
    assert body["job"]["taskId"] is None
    assert body["job"]["appName"] == "differentialexpression"
    assert body["analysis"]["revision"] == 1
    assert body["step"] is None


async def test_run_compute_writes_the_computation_into_the_analysis(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
) -> None:
    """The analysis is the SSOT the volcano reads, so the tab's run writes it."""
    del de_wired
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    ran = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": computation_json()},
    )
    assert ran.status_code == 200
    assert ran.json()["job"]["jobId"] == JOB_ID

    read = await client.get(f"/api/v1/conversations/{conversation_id}/eda")
    assert read.status_code == 200
    computations = read.json()["descriptor"]["computations"]
    assert len(computations) == 1
    assert computations[0]["descriptor"]["type"] == "differentialexpression"
    assert read.json()["analysis"]["numComputations"] == 1

    plotted = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={
            "datasetId": DATASET,
            "chart": "volcano",
            "effectSizeThreshold": 1.0,
            "significanceThreshold": 0.05,
            "effectDirection": "upAndDown",
        },
    )
    assert plotted.status_code == 200
    assert plotted.json()["totalPoints"] == 201


async def test_repeating_the_identical_run_compute_writes_the_analysis_once(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
) -> None:
    """The identical action is the status poll, and a poll writes nothing."""
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)
    body = {"action": "run-compute", "computation": computation_json()}
    url = f"/api/v1/conversations/{conversation_id}/eda"

    first = await client.patch(url, json=body)
    second = await client.patch(url, json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["job"]["jobId"] == JOB_ID
    assert de_wired.patches == 1
    assert len(de_wired.detail.descriptor.computations) == 1


async def test_a_changed_configuration_writes_the_analysis_again(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
) -> None:
    """Another configuration is another compute, so the document follows it."""
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)
    url = f"/api/v1/conversations/{conversation_id}/eda"

    await client.patch(
        url, json={"action": "run-compute", "computation": computation_json()}
    )
    changed = await client.patch(
        url,
        json={
            "action": "run-compute",
            "computation": computation_json(
                value_variable="SEQUENCE_READ_COUNT_ANTISENSE"
            ),
        },
    )

    assert changed.status_code == 200
    assert de_wired.patches == 2
    computations = de_wired.detail.descriptor.computations
    assert len(computations) == 1
    value_variable = computations[0].descriptor.configuration.value_variable
    assert value_variable.variable_id == "SEQUENCE_READ_COUNT_ANTISENSE"


async def test_run_compute_refuses_a_config_the_study_rejects_before_the_job(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
) -> None:
    """A label outside the vocabulary reaches a failed job, so it never starts."""
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "run-compute",
            "computation": computation_json(group_a="hypothermic"),
        },
    )
    assert response.status_code == 422
    assert "hypothermic" in json.dumps(response.json())
    assert de_wired.detail.descriptor.computations == []


async def test_export_step_carries_the_thresholds_into_the_exported_step(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
    hermetic_wdk: None,
) -> None:
    """The thresholds the researcher chose ride in the step's analysis spec."""
    del de_wired, hermetic_wdk
    client, conversation_id = thread
    await bind_thread(session_maker, conversation_id)
    await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": computation_json()},
    )

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "export-step",
            "thresholds": {
                "effectSizeThreshold": 1.0,
                "significanceThreshold": 0.05,
                "effectDirection": "upAndDown",
            },
        },
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
    }
    assert body["analysis"]["revision"] == 2


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
        json={"action": "export-step", "thresholds": None},
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
