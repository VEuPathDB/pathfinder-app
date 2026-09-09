"""The recorded EDA deployment and the thread the conversation routes act on."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.types import JSONObject
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
)

from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests._support.eda_wire import (
    AnalysisStore,
    eda_transport,
    wire_eda,
)
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

DATASET = "DS_53f554ec6a"
STUDY = "STUDY_53f554ec6a"
ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
SPECIES = "VAR_035294d0"
ANALYSIS = "t4fszEJ"

PHENOTYPE = "study_detail_phenotype"
SAMPLE_ENTITY = "ENT_8151325d"
COUNTS_ENTITY = "ENT_fd574cd6"
CONDITION = "VAR_081ab087"


def computation_json(
    group_a: str = "febrile",
    value_variable: str = "SEQUENCE_READ_COUNT_SENSE",
) -> JSONObject:
    """A differential expression the DE study declares every variable of."""
    return {
        "type": "differentialexpression",
        "configuration": {
            "identifierVariable": {
                "entityId": COUNTS_ENTITY,
                "variableId": "VEUPATHDB_GENE_ID",
            },
            "valueVariable": {
                "entityId": COUNTS_ENTITY,
                "variableId": value_variable,
            },
            "comparator": {
                "variable": {"entityId": SAMPLE_ENTITY, "variableId": CONDITION},
                "groupA": [{"label": group_a}],
                "groupB": [{"label": "normal"}],
            },
        },
    }


def detail() -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS,
        display_name="berghei subset",
        study_id=DATASET,
        num_filters=1,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=[
                    EdaStringSetFilter(
                        entity_id=ENTITY,
                        variable_id=SPECIES,
                        string_set=["P. berghei"],
                    )
                ]
            )
        ),
    )


def _emptydetail(study_id: str) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS,
        display_name="de analysis",
        study_id=study_id,
        num_filters=0,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(),
    )


@pytest.fixture
def phenotype_wired(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The phenotype study and its analysis document, over the recorded wire."""
    store = AnalysisStore(detail=detail())
    wire_eda(
        monkeypatch,
        eda_transport(study_id=STUDY, study_fixture=PHENOTYPE, store=store),
    )
    return store


@pytest.fixture
def empty_subset_wired(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The same study, where every filtered count comes back empty."""
    store = AnalysisStore(detail=detail())
    wire_eda(
        monkeypatch,
        eda_transport(
            study_id=STUDY,
            study_fixture=PHENOTYPE,
            store=store,
            count=0,
        ),
    )
    return store


@pytest.fixture
def de_wired(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The differential-expression study, and a document a PATCH rewrites."""
    store = AnalysisStore(detail=_emptydetail(DATASET))
    wire_eda(
        monkeypatch,
        eda_transport(
            study_id=STUDY,
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
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
        )
        session.add(conversation)
        await session.commit()
    client = first_frame_client_for(app, user.id, wdk_token="test-token")
    async with client:
        yield client, conversation.id


async def bind_thread(
    session_maker: async_sessionmaker[AsyncSession], conversation_id: UUID
) -> None:
    await ConversationAnalysesRepository(session_factory=session_maker).bind(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=DATASET,
        analysis_id=ANALYSIS,
    )
