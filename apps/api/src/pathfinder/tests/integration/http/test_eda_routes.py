"""The EDA REST surface the tab hydrates from."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.integrations.eda.client import EdaClient
from pathfinder.integrations.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaVariableSpec,
)
from pathfinder.integrations.embeddings.study_index import sync_study_index
from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.platform.context import veupathdb_auth_token_ctx
from pathfinder.services.eda import authoring, catalog, compute
from pathfinder.tests.integration.http.conftest import (
    client_for,
    first_frame_client_for,
    make_user,
)
from pathfinder.transport.http.routers import eda as eda_router

FIXTURES = (
    Path(__file__).resolve().parents[2] / "unit" / "integrations" / "eda" / "fixtures"
)

pytestmark = pytest.mark.asyncio

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"
_HIDDEN = "VAR_71b4a7d4"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


_FIXTURE_BY_SUFFIX = {
    "/permissions": "permissions.json",
    "/eda/studies": "studies_list.json",
    f"/eda/studies/{_STUDY}": "study_detail_phenotype.json",
    "/distribution": "distribution_categorical.json",
    "/statistics": "volcano_statistics.json",
}


def _body(path: str, counts: list[int]) -> object | None:
    """The recorded response for one EDA path, or None when there is none."""
    for suffix, name in _FIXTURE_BY_SUFFIX.items():
        if path.endswith(suffix):
            return _fixture(name)
    if path.endswith("/count"):
        return {"count": counts.pop(0)}
    if "/visualizations/" in path:
        return _fixture("volcano_statistics.json")
    return None


def _route(counts: list[int]) -> httpx.MockTransport:
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
        base_url="https://plasmodb.org/eda", transport=_route([4011, 4279])
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


async def test_a_study_search_answers_with_cards(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        "/api/v1/eda/studies", params={"q": "phenotype", "siteId": "plasmodb"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["studies"]
    first = body["studies"][0]
    assert set(first) >= {
        "datasetId",
        "studyId",
        "displayName",
        "canSubset",
        "canExportRows",
        "relevance",
    }
    assert first["relevance"] > 0.0


async def test_a_study_search_with_no_query_lists_the_catalog_by_name(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get("/api/v1/eda/studies", params={"siteId": "plasmodb"})
    assert response.status_code == 200
    studies = response.json()["studies"]
    assert studies
    names = [study["displayName"] for study in studies]
    assert names == sorted(names)
    assert all(study["relevance"] == 0.0 for study in studies)


async def test_a_study_detail_carries_the_entity_tree_and_the_gene_entity(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{_DATASET}", params={"siteId": "plasmodb"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["datasetId"] == _DATASET
    assert body["studyId"] == _STUDY
    assert body["geneEntityId"] == _ENTITY
    assert body["canSubset"] is True
    entities = {e["entityId"] for e in body["entities"]}
    assert _ENTITY in entities
    variables = body["variables"]
    assert any(v["variableId"] == _SPECIES for v in variables)


async def test_a_study_detail_for_one_entity_carries_that_entity_only(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """A study can declare thousands of variables, so the tab asks per entity."""
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{_DATASET}",
        params={"siteId": "plasmodb", "entityId": _ENTITY},
    )
    assert response.status_code == 200
    variables = response.json()["variables"]
    assert variables
    assert {v["entityId"] for v in variables} == {_ENTITY}
    species = next(v for v in variables if v["variableId"] == _SPECIES)
    assert species["filterType"] == "stringSet"
    assert "P. berghei" in species["vocabulary"]


async def test_a_study_detail_carries_the_hide_from_advice_of_each_variable(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The tab lists what the site lists, so it needs the site's advice."""
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{_DATASET}",
        params={"siteId": "plasmodb", "entityId": _ENTITY},
    )
    assert response.status_code == 200
    hide_from = {v["variableId"]: v["hideFrom"] for v in response.json()["variables"]}
    assert hide_from[_HIDDEN] == ["variableTree"]
    assert hide_from[_SPECIES] == []


async def test_a_study_detail_for_an_unknown_entity_is_a_404(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        f"/api/v1/eda/studies/{_DATASET}",
        params={"siteId": "plasmodb", "entityId": "NO_SUCH_ENTITY"},
    )
    assert response.status_code == 404
    assert "NO_SUCH_ENTITY" in json.dumps(response.json())


async def test_an_unknown_dataset_is_a_404_naming_the_id(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.get(
        "/api/v1/eda/studies/DS_nope", params={"siteId": "plasmodb"}
    )
    assert response.status_code == 404
    assert "DS_nope" in json.dumps(response.json())


async def test_a_request_with_no_wdk_token_is_refused(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> None:
    """EDA refuses a guest, so a request naming no registered login is a 401."""
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        user = await make_user(session)
    async with client_for(app, user.id) as client:
        response = await client.get(
            "/api/v1/eda/studies", params={"siteId": "plasmodb"}
        )
    assert response.status_code == 401
    assert response.json()["code"] == "WDK_LOGIN_REQUIRED"


async def test_a_missing_site_id_is_a_422(
    api_client: tuple[httpx.AsyncClient, UUID],
) -> None:
    client, _user_id = api_client
    response = await client.get("/api/v1/eda/studies")
    assert response.status_code == 422


async def test_count_answers_with_the_service_count(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/count",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": _DATASET,
            "entityId": _ENTITY,
            "filters": [
                {
                    "entityId": _ENTITY,
                    "variableId": _SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. berghei"],
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entityId"] == _ENTITY
    assert body["count"] == 4011
    assert body["unfilteredCount"] == 4279


async def test_count_refuses_an_out_of_vocabulary_value_with_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The service answers 200 with count 0, so the route must refuse first."""
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/count",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": _DATASET,
            "entityId": _ENTITY,
            "filters": [
                {
                    "entityId": _ENTITY,
                    "variableId": _SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. vivax"],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "P. vivax" in json.dumps(response.json())


async def test_count_refuses_an_unknown_filter_type_with_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    """The discriminated union refuses stringPrefixSet before any wire call."""
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/count",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": _DATASET,
            "entityId": _ENTITY,
            "filters": [
                {
                    "entityId": _ENTITY,
                    "variableId": "V",
                    "type": "stringPrefixSet",
                    "prefixSet": ["ab"],
                }
            ],
        },
    )
    assert response.status_code == 422


async def test_distribution_answers_with_labels_and_values_of_equal_length(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/distribution",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": _DATASET,
            "entityId": _ENTITY,
            "variableId": _SPECIES,
            "filters": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["variableId"] == _SPECIES
    assert body["variableDisplayName"] == "Species"
    assert len(body["labels"]) == len(body["values"])
    assert body["labels"][0] == "P. berghei"
    assert body["numVarValues"] == 8409
    assert body["isMultiValued"] is True


async def test_distribution_refuses_an_out_of_vocabulary_filter_with_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/distribution",
        params={"siteId": "plasmodb"},
        json={
            "datasetId": _DATASET,
            "entityId": _ENTITY,
            "variableId": _SPECIES,
            "filters": [
                {
                    "entityId": _ENTITY,
                    "variableId": _SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. vivax"],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "P. vivax" in json.dumps(response.json())


async def test_a_chart_kind_outside_the_union_is_a_422(
    api_client: tuple[httpx.AsyncClient, UUID], eda_wired: EdaClient
) -> None:
    del eda_wired
    client, _user_id = api_client
    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(uuid4())},
        json={"datasetId": _DATASET, "chart": "pie"},
    )
    assert response.status_code == 422


def _analysis(*, with_computation: bool) -> EdaAnalysisDetail:
    computations = (
        [
            EdaComputation(
                computation_id="c1",
                descriptor=EdaComputationDescriptor(
                    configuration=EdaDifferentialExpressionConfig(
                        identifier_variable=EdaVariableSpec(
                            entity_id=_ENTITY, variable_id="VAR_gene"
                        ),
                        value_variable=EdaVariableSpec(
                            entity_id=_ENTITY, variable_id="VAR_counts"
                        ),
                        comparator=EdaComparator(
                            variable=EdaVariableSpec(
                                entity_id=_ENTITY, variable_id="VAR_state"
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
        study_id=_DATASET,
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
        conversation = Conversation(id=uuid4(), user_id=user.id)
        session.add(conversation)
        await session.commit()
    async with first_frame_client_for(app, user.id, wdk_token="test-token") as client:
        yield client, conversation.id, user.id


async def test_viz_answers_with_the_thresholded_volcano(
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
        dataset_id=_DATASET,
        analysis_id="t4fszEJ",
    )

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        assert analysis_id == "t4fszEJ"
        return _analysis(with_computation=True)

    monkeypatch.setattr(eda_router, "read_analysis", read)

    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={
            "datasetId": _DATASET,
            "chart": "volcano",
            "effectSizeThreshold": 1.0,
            "significanceThreshold": 0.05,
            "effectDirection": "upAndDown",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chart"] == "volcano"
    assert body["effectSizeLabel"] == "log2(Fold Change)"
    assert body["totalPoints"] == 201
    assert body["retainedPoints"] == 67
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


async def test_viz_keeps_only_the_up_side_when_the_direction_says_so(
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
        dataset_id=_DATASET,
        analysis_id="t4fszEJ",
    )

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del analysis_id
        return _analysis(with_computation=True)

    monkeypatch.setattr(eda_router, "read_analysis", read)

    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={
            "datasetId": _DATASET,
            "chart": "volcano",
            "effectSizeThreshold": 1.0,
            "significanceThreshold": 0.05,
            "effectDirection": "upOnly",
        },
    )
    assert response.status_code == 200
    retained = [p for p in response.json()["points"] if p["retained"]]
    assert retained
    assert all(p["effectSize"] > 0 for p in retained)


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
        dataset_id=_DATASET,
        analysis_id="t4fszEJ",
    )

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del analysis_id
        return _analysis(with_computation=False)

    monkeypatch.setattr(eda_router, "read_analysis", read)

    response = await client.post(
        "/api/v1/eda/viz",
        params={"siteId": "plasmodb", "conversationId": str(conversation_id)},
        json={
            "datasetId": _DATASET,
            "chart": "volcano",
            "effectSizeThreshold": 1.0,
            "significanceThreshold": 0.05,
        },
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
        json={"datasetId": _DATASET, "chart": "volcano"},
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
        conversation = Conversation(id=uuid4(), user_id=owner.id)
        session.add(conversation)
        await session.commit()
    async with first_frame_client_for(app, other.id, wdk_token="test-token") as client:
        response = await client.post(
            "/api/v1/eda/viz",
            params={"siteId": "plasmodb", "conversationId": str(conversation.id)},
            json={"datasetId": _DATASET, "chart": "volcano"},
        )
    assert response.status_code == 404
