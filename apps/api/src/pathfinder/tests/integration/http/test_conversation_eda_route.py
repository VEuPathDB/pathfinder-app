"""The conversation's bound analysis: read it, mutate it, and clear it."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.types import JSONObject
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.integrations.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
)
from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.services.catalog.eda_backed import COMPUTE_QUERY, SUBSET_QUERY
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests._support.eda_wire import (
    JOB_ID,
    AnalysisStore,
    eda_transport,
    wire_eda,
)
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

pytestmark = pytest.mark.asyncio

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"
_ANALYSIS = "t4fszEJ"

_PHENOTYPE = "study_detail_phenotype"
_SAMPLE_ENTITY = "ENT_8151325d"
_COUNTS_ENTITY = "ENT_fd574cd6"
_CONDITION = "VAR_081ab087"


def _computation_json(
    group_a: str = "febrile",
    value_variable: str = "SEQUENCE_READ_COUNT_SENSE",
) -> JSONObject:
    """A differential expression the DE study declares every variable of."""
    return {
        "type": "differentialexpression",
        "configuration": {
            "identifierVariable": {
                "entityId": _COUNTS_ENTITY,
                "variableId": "VEUPATHDB_GENE_ID",
            },
            "valueVariable": {
                "entityId": _COUNTS_ENTITY,
                "variableId": value_variable,
            },
            "comparator": {
                "variable": {"entityId": _SAMPLE_ENTITY, "variableId": _CONDITION},
                "groupA": [{"label": group_a}],
                "groupB": [{"label": "normal"}],
            },
        },
    }


def _detail() -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=_ANALYSIS,
        display_name="berghei subset",
        study_id=_DATASET,
        num_filters=1,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=[
                    EdaStringSetFilter(
                        entity_id=_ENTITY,
                        variable_id=_SPECIES,
                        string_set=["P. berghei"],
                    )
                ]
            )
        ),
    )


def _empty_detail(study_id: str) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=_ANALYSIS,
        display_name="de analysis",
        study_id=study_id,
        num_filters=0,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(),
    )


@pytest.fixture
def phenotype_wired(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The phenotype study and its analysis document, over the recorded wire."""
    store = AnalysisStore(detail=_detail())
    wire_eda(
        monkeypatch,
        eda_transport(study_id=_STUDY, study_fixture=_PHENOTYPE, store=store),
    )
    return store


@pytest.fixture
def empty_subset_wired(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The same study, where every filtered count comes back empty."""
    store = AnalysisStore(detail=_detail())
    wire_eda(
        monkeypatch,
        eda_transport(
            study_id=_STUDY,
            study_fixture=_PHENOTYPE,
            store=store,
            count=0,
        ),
    )
    return store


@pytest.fixture
def de_wired(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The differential-expression study, and a document a PATCH rewrites."""
    store = AnalysisStore(detail=_empty_detail(_DATASET))
    wire_eda(
        monkeypatch,
        eda_transport(
            study_id=_STUDY,
            study_fixture="study_detail_de",
            store=store,
            count=66132,
        ),
    )
    return store


@pytest.fixture
def hermetic_wdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """WDK is not reached: the commit reports a push it never sent."""

    async def no_push(**_kwargs: object) -> _WDKCommitOutcome:
        return _WDKCommitOutcome(
            succeeded_step_ids=[], failed_step_ids=[], sync_result=None
        )

    monkeypatch.setattr(commit, "_commit_to_wdk", no_push)


@pytest.fixture
async def thread(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[tuple[httpx.AsyncClient, UUID]]:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        user = await make_user(session)
        conversation = Conversation(id=uuid4(), user_id=user.id)
        session.add(conversation)
        await session.commit()
    client = first_frame_client_for(app, user.id, wdk_token="test-token")
    async with client:
        yield client, conversation.id


async def _bind(
    session_maker: async_sessionmaker[AsyncSession], conversation_id: UUID
) -> None:
    await ConversationAnalysesRepository(session_factory=session_maker).bind(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=_ANALYSIS,
    )


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
    await _bind(session_maker, conversation_id)

    response = await client.get(f"/api/v1/conversations/{conversation_id}/eda")
    assert response.status_code == 200
    body = response.json()
    analysis = body["analysis"]
    assert analysis["analysisId"] == _ANALYSIS
    assert analysis["datasetId"] == _DATASET
    assert analysis["siteId"] == "plasmodb"
    assert analysis["studyId"] == _STUDY
    assert analysis["studyDisplayName"]
    assert analysis["displayName"] == "berghei subset"
    assert analysis["numFilters"] == 1
    assert analysis["revision"] == 0
    assert analysis["filterSummaries"] == ["Species is one of P. berghei"]
    assert analysis["filters"][0]["stringSet"] == ["P. berghei"]
    assert analysis["canExportRows"] is True
    assert analysis["entityCounts"] == [
        {
            "entityId": _ENTITY,
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
    await _bind(session_maker, conversation_id)

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
    await _bind(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "set-filters",
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
    assert phenotype_wired.patches == 1
    written = phenotype_wired.detail.descriptor.subset.descriptor
    assert [f.variable_id for f in written] == [_SPECIES]
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
    await _bind(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "set-filters",
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


async def test_unbinding_clears_the_binding(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    client, conversation_id = thread
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    await _bind(session_maker, conversation_id)
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
        json={"action": "bind", "siteId": "plasmodb", "datasetId": _DATASET},
    )
    assert response.status_code == 200
    assert len(phenotype_wired.created) == 1
    body = response.json()
    assert body["analysis"]["datasetId"] == _DATASET
    assert body["analysis"]["revision"] == 1
    assert body["job"] is None
    repo = ConversationAnalysesRepository(session_factory=session_maker)
    bound = await repo.get(conversation_id=conversation_id)
    assert bound is not None
    assert bound.dataset_id == _DATASET


async def test_run_compute_answers_with_the_job_reference(
    thread: tuple[httpx.AsyncClient, UUID],
    session_maker: async_sessionmaker[AsyncSession],
    de_wired: AnalysisStore,
) -> None:
    """The tab gets the job the compute service submitted, and the new revision."""
    del de_wired
    client, conversation_id = thread
    await _bind(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": _computation_json()},
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
    await _bind(session_maker, conversation_id)

    ran = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": _computation_json()},
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
            "datasetId": _DATASET,
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
    await _bind(session_maker, conversation_id)
    body = {"action": "run-compute", "computation": _computation_json()}
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
    await _bind(session_maker, conversation_id)
    url = f"/api/v1/conversations/{conversation_id}/eda"

    await client.patch(
        url, json={"action": "run-compute", "computation": _computation_json()}
    )
    changed = await client.patch(
        url,
        json={
            "action": "run-compute",
            "computation": _computation_json(
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
    await _bind(session_maker, conversation_id)

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={
            "action": "run-compute",
            "computation": _computation_json(group_a="hypothermic"),
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
    await _bind(session_maker, conversation_id)
    await client.patch(
        f"/api/v1/conversations/{conversation_id}/eda",
        json={"action": "run-compute", "computation": _computation_json()},
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
    await _bind(session_maker, conversation_id)

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
        conversation = Conversation(id=uuid4(), user_id=owner.id)
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
