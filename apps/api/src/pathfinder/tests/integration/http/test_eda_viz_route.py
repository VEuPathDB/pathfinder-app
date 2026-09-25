"""The volcano route: what it draws, and the conflicts it refuses."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaClient,
    EdaComparator,
    EdaComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaLabeledRange,
    EdaVariableSpec,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)

from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.http._eda_routes import (
    DATASET,
    ENTITY,
    eda_wired,
)
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)
from pathfinder.transport.http.routers import eda

pytestmark = pytest.mark.asyncio

__all__ = ["eda_wired"]


def _analysis(
    *, with_computation: bool, volcano: EdaVolcanoConfiguration | None = None
) -> EdaAnalysisDetail:
    visualizations = (
        []
        if volcano is None
        else [
            EdaVisualization(
                visualization_id="v1",
                descriptor=EdaVolcanoDescriptor(configuration=volcano),
            )
        ]
    )
    computations = (
        [
            EdaComputation(
                computation_id="c1",
                visualizations=visualizations,
                descriptor=EdaDifferentialExpressionDescriptor(
                    configuration=EdaDifferentialExpressionConfig(
                        identifier_variable=EdaVariableSpec(
                            entity_id=ENTITY, variable_id="VAR_gene"
                        ),
                        value_variable=EdaVariableSpec(
                            entity_id=ENTITY, variable_id="VAR_counts"
                        ),
                        comparator=EdaComparator(
                            variable=EdaVariableSpec(
                                entity_id=ENTITY, variable_id="VAR_state"
                            ),
                            group_a=[EdaLabeledRange(label="febrile")],
                            group_b=[EdaLabeledRange(label="normal")],
                        ),
                    )
                ),
            )
        ]
        if with_computation
        else []
    )
    return EdaAnalysisDetail(
        analysis_id="t4fszEJ",
        display_name="berghei subset",
        study_id=DATASET,
        descriptor=EdaAnalysisDescriptor(computations=computations),
    )


@pytest.fixture
async def owned_thread(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[tuple[httpx.AsyncClient, UUID, UUID]]:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        user = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
        )
        session.add(conversation)
        await session.commit()
    async with first_frame_client_for(app, user.id, wdk_token="test-token") as client:
        yield client, conversation.id, user.id


async def test_viz_draws_the_default_cut_when_the_analysis_stores_none(
    owned_thread: tuple[httpx.AsyncClient, UUID, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    eda_wired: EdaClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del eda_wired
    client, conversation_id, _user_id = owned_thread
    await ConversationAnalysesRepository(session_factory=session_maker).bind(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=DATASET,
        analysis_id="t4fszEJ",
    )

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        assert analysis_id == "t4fszEJ"
        return _analysis(with_computation=True)

    monkeypatch.setattr(eda, "read_analysis", read)

    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={"chart": "volcano"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chart"] == "volcano"
    assert (
        body["effectSizeThreshold"],
        body["significanceThreshold"],
        body["effectDirection"],
    ) == (1.0, 0.05, "upAndDown")
    assert body["effectSizeLabel"] == "log2(Fold Change)"
    assert body["totalPoints"] == 201
    assert body["retainedPoints"] == 67
    assert body["comparison"] == {"groupA": ["febrile"], "groupB": ["normal"]}
    # Every row with a readable effect size has an x coordinate, so it is
    # plotted; the one row with no p-value is drawn and never retained.
    assert len(body["points"]) == 201
    silent = [p for p in body["points"] if p["pValue"] is None]
    assert len(silent) == 1
    assert silent[0]["adjustedPValue"] is None
    assert silent[0]["retained"] is False
    retained = [p for p in body["points"] if p["retained"]]
    assert len(retained) == body["retainedPoints"]
    assert all(abs(p["effectSize"]) >= 1.0 for p in retained)
    assert all(p["pValue"] <= 0.05 for p in retained)


async def test_viz_draws_the_cut_the_analysis_stores(
    owned_thread: tuple[httpx.AsyncClient, UUID, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    eda_wired: EdaClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del eda_wired
    client, conversation_id, _user_id = owned_thread
    await ConversationAnalysesRepository(session_factory=session_maker).bind(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=DATASET,
        analysis_id="t4fszEJ",
    )

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del analysis_id
        return _analysis(
            with_computation=True,
            volcano=EdaVolcanoConfiguration(
                effect_size_threshold=2.0,
                significance_threshold=0.01,
                effect_direction="upOnly",
            ),
        )

    monkeypatch.setattr(eda, "read_analysis", read)

    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={"chart": "volcano"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["effectSizeThreshold"],
        body["significanceThreshold"],
        body["effectDirection"],
    ) == (2.0, 0.01, "upOnly")
    retained = [p for p in body["points"] if p["retained"]]
    assert retained
    assert len(retained) == body["retainedPoints"]
    assert all(p["effectSize"] >= 2.0 for p in retained)
    assert all(p["pValue"] <= 0.01 for p in retained)


async def test_viz_on_an_analysis_with_no_computation_is_a_409(
    owned_thread: tuple[httpx.AsyncClient, UUID, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    eda_wired: EdaClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The visualization endpoint never starts a compute."""
    del eda_wired
    client, conversation_id, _user_id = owned_thread
    await ConversationAnalysesRepository(session_factory=session_maker).bind(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=DATASET,
        analysis_id="t4fszEJ",
    )

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del analysis_id
        return _analysis(with_computation=False)

    monkeypatch.setattr(eda, "read_analysis", read)

    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={"chart": "volcano"},
    )
    assert response.status_code == 409
    assert "no comparison has run" in json.dumps(response.json()).lower()


async def test_viz_on_a_thread_with_no_open_analysis_is_a_409(
    owned_thread: tuple[httpx.AsyncClient, UUID, UUID],
) -> None:
    client, conversation_id, _user_id = owned_thread
    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={"chart": "volcano"},
    )
    assert response.status_code == 409
    assert "no study is open" in json.dumps(response.json()).lower()


async def test_viz_on_another_users_thread_is_a_404(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> None:
    """The viz route reads a thread, so it refuses a thread the caller lacks."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        owner = await make_user(session)
        other = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=owner.id
        )
        session.add(conversation)
        await session.commit()
    async with first_frame_client_for(app, other.id, wdk_token="test-token") as client:
        response = await client.post(
            "/api/v1/eda/viz",
            params={"siteId": "plasmodb", "conversationId": str(conversation.id)},
            json={"chart": "volcano"},
        )
    assert response.status_code == 404
