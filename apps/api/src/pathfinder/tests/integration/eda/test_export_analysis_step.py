"""The tab's export and the state it reports, driven through the real commit."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select
from veupathdb.eda import EdaAnalysisDetail, EdaVolcanoConfiguration
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.responses import ConversationResponse
from pathfinder.services.eda import binding
from pathfinder.services.eda.binding import mutated_analysis_state
from pathfinder.services.eda.gene_subset import NoGeneSubsetError
from pathfinder.services.eda.steps import export_analysis_step
from pathfinder.tests._support.eda_doubles import ANALYSIS_ID
from pathfinder.tests._support.eda_step_doubles import (
    DE_DATASET,
    SAMPLE_ONLY_REFUSAL,
    de_analysis,
    phenotype_subset,
    sample_filter,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_STUDY,
    AnalysisStore,
)
from pathfinder.tests._support.step_params import string_param
from pathfinder.tests.integration.eda._export_wiring import (
    added_step,
    hermetic_wdk,
    open_analysis,
    persisted_ast,
    search_names,
    thread,
)

pytestmark = pytest.mark.asyncio

__all__ = ["hermetic_wdk", "open_analysis", "thread"]

Open = Callable[[UUID, EdaAnalysisDetail], Awaitable[AnalysisStore]]


async def test_a_subset_export_adds_the_generic_subset_step(
    thread: tuple[UUID, UUID],
    open_analysis: Open,
    hermetic_wdk: list[Any],
) -> None:
    """No thresholds means the subset's genes, carried by the two parameters."""
    conversation_id, user_id = thread
    await open_analysis(conversation_id, phenotype_subset())

    async with async_session_factory() as session:
        refreshed = await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            reads_the_volcano=False,
        )

    step = await added_step(conversation_id)
    assert step.search_name == SUBSET_QUERY
    assert string_param(step, "eda_dataset_id") == PHENOTYPE_DATASET
    spec = json.loads(string_param(step, "eda_analysis_spec"))
    assert spec["studyId"] == PHENOTYPE_DATASET
    assert spec["descriptor"]["subset"]["descriptor"][0]["stringSet"] == ["P. berghei"]
    assert step.display_name == "berghei subset"
    assert ConversationResponse.model_validate(refreshed).id == conversation_id


async def test_a_volcano_export_adds_the_compute_step_with_the_stored_cut(
    thread: tuple[UUID, UUID],
    open_analysis: Open,
    hermetic_wdk: list[Any],
) -> None:
    """The cut the analysis stores rides in the analysis spec."""
    conversation_id, user_id = thread
    await open_analysis(
        conversation_id,
        de_analysis(
            filters=[sample_filter()],
            with_computation=True,
            volcano=EdaVolcanoConfiguration(
                effect_size_threshold=2.0,
                significance_threshold=0.01,
                effect_direction="upOnly",
            ),
        ),
    )

    async with async_session_factory() as session:
        await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            reads_the_volcano=True,
        )

    step = await added_step(conversation_id)
    assert step.search_name == COMPUTE_QUERY
    assert string_param(step, "eda_dataset_id") == DE_DATASET
    assert set(step.parameters) == {"eda_dataset_id", "eda_analysis_spec"}
    spec = json.loads(string_param(step, "eda_analysis_spec"))
    volcano = spec["descriptor"]["computations"][0]["visualizations"][0]
    assert volcano["descriptor"]["configuration"] == {
        "effectSizeThreshold": 2.0,
        "significanceThreshold": 0.01,
        "effectDirection": "upOnly",
    }
    assert step.display_name == "Genes higher in normal than in febrile"


async def test_the_exported_step_is_persisted_on_the_thread(
    thread: tuple[UUID, UUID],
    open_analysis: Open,
    hermetic_wdk: list[Any],
) -> None:
    """The refreshed payload is read back from the row the commit wrote."""
    del hermetic_wdk
    conversation_id, user_id = thread
    await open_analysis(conversation_id, phenotype_subset())

    async with async_session_factory() as session:
        await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            reads_the_volcano=False,
        )

    async with async_session_factory() as session:
        stored = await session.scalar(
            select(ConversationStrategy.strategy_ast).where(
                ConversationStrategy.conversation_id == conversation_id
            )
        )
    assert stored is not None
    assert SUBSET_QUERY in json.dumps(stored)


async def test_a_subset_of_samples_is_refused_and_writes_no_step(
    thread: tuple[UUID, UUID],
    open_analysis: Open,
    hermetic_wdk: list[Any],
) -> None:
    """A step exports genes, and a subset of samples selects none."""
    conversation_id, user_id = thread
    await open_analysis(conversation_id, de_analysis(filters=[sample_filter()]))

    async with async_session_factory() as session:
        with pytest.raises(NoGeneSubsetError) as refusal:
            await export_analysis_step(
                session=session,
                conversation_id=conversation_id,
                user_id=user_id,
                reads_the_volcano=False,
            )

    assert refusal.value.status == 422
    assert refusal.value.detail == SAMPLE_ONLY_REFUSAL
    assert search_names(await persisted_ast(conversation_id)) == ["GenesByTaxon"]
    assert hermetic_wdk == []


async def test_an_export_on_an_unbound_thread_is_refused(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        with pytest.raises(binding.NoOpenAnalysisError) as excinfo:
            await export_analysis_step(
                session=session,
                conversation_id=conversation_id,
                user_id=user_id,
                reads_the_volcano=False,
            )
    assert excinfo.value.status == 409


async def test_the_mutated_state_counts_the_write_and_names_the_study(
    thread: tuple[UUID, UUID],
    open_analysis: Open,
) -> None:
    """Two surfaces edit one analysis, so each answer says which write it is."""
    conversation_id, _user_id = thread
    await open_analysis(conversation_id, phenotype_subset())

    first = await mutated_analysis_state(conversation_id=conversation_id)
    second = await mutated_analysis_state(conversation_id=conversation_id)

    assert first.revision == 1
    assert second.revision == 2
    assert first.dataset_id == PHENOTYPE_DATASET
    assert first.study_id == PHENOTYPE_STUDY
    assert first.analysis_id == ANALYSIS_ID
    assert first.num_filters == 1
    assert first.filter_summaries == ["Species is one of P. berghei"]
    assert first.filters[0]["stringSet"] == ["P. berghei"]
    assert first.can_export_rows is True


async def test_the_mutated_state_on_an_unbound_thread_is_refused(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    with pytest.raises(binding.NoOpenAnalysisError):
        await mutated_analysis_state(conversation_id=uuid4())


async def test_an_export_beside_an_existing_strategy_is_a_detached_root_and_is_not_pushed(
    thread: tuple[UUID, UUID],
    open_analysis: Open,
    hermetic_wdk: list[Any],
) -> None:
    """A thread that already holds a strategy gains a SECOND root.

    The step is a new root beside the existing one, so the commit's pushable
    branch is still the old root and the EDA step does not reach WDK here.
    """
    conversation_id, user_id = thread
    await open_analysis(conversation_id, phenotype_subset())

    async with async_session_factory() as session:
        await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            reads_the_volcano=False,
        )

    ast = await persisted_ast(conversation_id)
    assert ast.root.search_name == "GenesByTaxon"
    assert [root.search_name for root in ast.detached_roots] == [SUBSET_QUERY]

    pushed = hermetic_wdk[-1]
    assert search_names(pushed) == ["GenesByTaxon"]


async def _thread_without_a_strategy(*, with_empty_row: bool) -> tuple[UUID, UUID]:
    """A thread whose strategy was never built."""
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
            )
        )
        await session.flush()
        if with_empty_row:
            session.add(ConversationStrategy(conversation_id=conversation_id))
        await session.commit()
    return conversation_id, user_id


@pytest.mark.parametrize("with_empty_row", [False, True])
async def test_an_export_on_a_thread_with_no_strategy_begins_it(
    patch_app_db_engine: None,
    db_cleaner: None,
    open_analysis: Open,
    hermetic_wdk: list[Any],
    with_empty_row: bool,
) -> None:
    """The export is the thread's first step, so it becomes the root and is pushed."""
    del patch_app_db_engine, db_cleaner
    conversation_id, user_id = await _thread_without_a_strategy(
        with_empty_row=with_empty_row
    )
    await open_analysis(conversation_id, phenotype_subset())

    async with async_session_factory() as session:
        refreshed = await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            reads_the_volcano=False,
        )

    ast = await persisted_ast(conversation_id)
    assert ast.root.search_name == SUBSET_QUERY
    assert ast.detached_roots == []
    assert search_names(hermetic_wdk[-1]) == [SUBSET_QUERY]
    payload = ConversationResponse.model_validate(refreshed)
    assert payload.root_step_id == ast.root.id
    assert [step.search_name for step in payload.steps] == [SUBSET_QUERY]
