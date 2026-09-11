"""The binding's revision counter, over the thread row it belongs to."""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from pydantic_ai import RunContext
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.models import EdaStringSetFilter

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.eda_doubles import (
    SPECIES_VARIABLE,
    analysis_detail,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
    AnalysisStore,
    eda_transport,
    wire_eda,
)
from pathfinder.tests._support.run_context import lead_run_context


@pytest.fixture(autouse=True)
def registered_account() -> Generator[None]:
    """The EDA catalog reads for one account, so a token must be in scope."""
    token = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(token)


@pytest.fixture(autouse=True)
def eda_deployment(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    """The recorded study and its analysis document, over the whole wire."""
    store = AnalysisStore(detail=analysis_detail())
    wire_eda(
        monkeypatch,
        eda_transport(
            study_id=PHENOTYPE_STUDY,
            study_fixture="study_detail_phenotype",
            store=store,
        ),
    )
    return store


@pytest.fixture
async def bound_thread(db_cleaner: None, patch_app_db_engine: None) -> UUID:
    """A real thread row, so the binding service can count its mutations."""
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    thread_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID, id=thread_id, user_id=user_id
            )
        )
        await session.commit()
    return thread_id


def _ctx_for(thread_id: UUID) -> RunContext[LeadDeps]:
    return lead_run_context(
        user_prompt="keep the berghei rows", conversation_id=thread_id
    )


async def test_an_identical_reading_mutation_adds_no_second_card(
    eda_deployment: AnalysisStore,
    bound_thread: UUID,
) -> None:
    """A mutation that leaves the card reading the same adds no second part.

    The binding still bumps its revision (test_binding covers the counter);
    the thread only shows a state the reader has not already seen.
    """
    ctx = _ctx_for(bound_thread)
    opened = await eda_analysis.open_eda_analysis(
        ctx, dataset_id=PHENOTYPE_DATASET, purpose="keep the berghei rows"
    )
    filtered = await eda_analysis.set_eda_filters(
        ctx,
        dataset_id=PHENOTYPE_DATASET,
        filters=[
            EdaStringSetFilter(
                entity_id=PHENOTYPE_ENTITY,
                variable_id=SPECIES_VARIABLE,
                string_set=["P. berghei"],
            )
        ],
    )
    assert opened.metadata[0].data["revision"] == 1
    assert eda_deployment.patches == 1
    assert filtered.metadata == []
