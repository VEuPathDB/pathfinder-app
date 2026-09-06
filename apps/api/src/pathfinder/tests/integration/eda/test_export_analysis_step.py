"""The tab's export and the state it reports, driven through the real commit."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters.values import SinglePickValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
    EdaVariableSpec,
)
from veupathdb_mcp.catalog.eda_backed import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.services.eda import binding
from pathfinder.services.eda.binding import mutated_analysis_state
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.steps import export_analysis_step
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests._support.eda_wire import (
    AnalysisStore,
    eda_transport,
    wire_eda,
)

pytestmark = pytest.mark.asyncio

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"
_ANALYSIS = "t4fszEJ"
_ROOT = "root"


def _computation() -> EdaComputation:
    return EdaComputation(
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


def _detail(*, with_computation: bool) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=_ANALYSIS,
        display_name="berghei subset",
        study_id=_DATASET,
        num_filters=1,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=[
                    EdaStringSetFilter(
                        entity_id=_ENTITY,
                        variable_id=_SPECIES,
                        string_set=["P. berghei"],
                    )
                ]
            ),
            computations=[_computation()] if with_computation else [],
        ),
    )


def _strategy_ast() -> dict[str, Any]:
    root = StrategyStepNode(
        id=_ROOT,
        search_name="GenesByTaxon",
        display_name="Taxon",
        parameters={"organism": SinglePickValue(value="Plasmodium falciparum 3D7")},
    )
    ast = StrategyAst(record_type="transcript", root=root)
    return ast.model_dump(by_alias=True, exclude_none=True, mode="json")


@pytest.fixture
def open_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., AnalysisStore]]:
    """Serve the phenotype study and one analysis document over the wire."""
    token = veupathdb_auth_token_ctx.set("t")

    def opened(*, with_computation: bool = False) -> AnalysisStore:
        store = AnalysisStore(detail=_detail(with_computation=with_computation))
        wire_eda(
            monkeypatch,
            eda_transport(
                study_id=_STUDY, study_fixture="study_detail_phenotype", store=store
            ),
        )
        return store

    yield opened
    veupathdb_auth_token_ctx.reset(token)


@pytest.fixture
def hermetic_wdk(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """WDK is not reached: the step push is recorded instead of sent."""
    pushed: list[Any] = []

    async def no_push(**kwargs: Any) -> _WDKCommitOutcome:
        pushed.append(kwargs["new_ast"])
        return _WDKCommitOutcome(
            succeeded_step_ids=[], failed_step_ids=[], sync_result=None
        )

    monkeypatch.setattr(commit, "_commit_to_wdk", no_push)
    return pushed


@pytest.fixture
async def thread(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[tuple[UUID, UUID]]:
    """A user, a conversation holding one step, and an analysis bound to it."""
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(Conversation(id=conversation_id, user_id=user_id))
        await session.flush()
        session.add(
            ConversationStrategy(
                conversation_id=conversation_id,
                strategy_ast=_strategy_ast(),
            )
        )
        await session.commit()
    await binding.bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=_ANALYSIS,
    )
    return conversation_id, user_id


def _walk(node: StrategyStepNode) -> Iterator[StrategyStepNode]:
    yield node
    for child in (node.primary_input, node.secondary_input):
        if child is not None:
            yield from _walk(child)


def _search_names(ast: StrategyAst) -> list[str]:
    """Every search the AST names, across its root and its detached roots."""
    return [
        node.search_name
        for root in (ast.root, *ast.detached_roots)
        for node in _walk(root)
    ]


async def _persisted_ast(conversation_id: UUID) -> StrategyAst:
    """The strategy the thread now holds, read back from its row."""
    async with async_session_factory() as session:
        stored = await session.scalar(
            select(ConversationStrategy.strategy_ast).where(
                ConversationStrategy.conversation_id == conversation_id
            )
        )
    assert stored is not None
    return StrategyAst.model_validate(stored)


async def _added_step(conversation_id: UUID) -> StrategyStepNode:
    """The EDA-backed leaf the export added to the thread's strategy."""
    ast = await _persisted_ast(conversation_id)
    roots = [ast.root, *ast.detached_roots]
    return next(
        node
        for root in roots
        for node in _walk(root)
        if node.search_name in {SUBSET_QUERY, COMPUTE_QUERY}
    )


async def test_a_subset_export_adds_the_generic_subset_step(
    thread: tuple[UUID, UUID],
    open_analysis: Callable[..., AnalysisStore],
    hermetic_wdk: list[Any],
) -> None:
    """No thresholds means the subset's genes, carried by the two parameters."""
    conversation_id, user_id = thread
    open_analysis()

    async with async_session_factory() as session:
        refreshed = await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    step = await _added_step(conversation_id)
    assert step.search_name == SUBSET_QUERY
    assert step.parameters["eda_dataset_id"].value == _DATASET
    spec = json.loads(step.parameters["eda_analysis_spec"].value)
    assert spec["studyId"] == _DATASET
    assert spec["descriptor"]["subset"]["descriptor"][0]["stringSet"] == ["P. berghei"]
    assert step.display_name == "berghei subset"
    assert refreshed["id"] == str(conversation_id)


async def test_a_volcano_export_adds_the_compute_step_with_the_thresholds(
    thread: tuple[UUID, UUID],
    open_analysis: Callable[..., AnalysisStore],
    hermetic_wdk: list[Any],
) -> None:
    """The thresholds the researcher chose ride in the analysis spec."""
    conversation_id, user_id = thread
    open_analysis(with_computation=True)

    async with async_session_factory() as session:
        await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            thresholds=VolcanoThresholds(
                effect_size_threshold=2.0,
                significance_threshold=0.01,
                effect_direction="upOnly",
            ),
        )

    step = await _added_step(conversation_id)
    assert step.search_name == COMPUTE_QUERY
    assert set(step.parameters) == {"eda_dataset_id", "eda_analysis_spec"}
    spec = json.loads(step.parameters["eda_analysis_spec"].value)
    volcano = spec["descriptor"]["computations"][0]["visualizations"][0]
    assert volcano["descriptor"]["configuration"] == {
        "effectSizeThreshold": 2.0,
        "significanceThreshold": 0.01,
        "effectDirection": "upOnly",
    }


async def test_the_exported_step_is_persisted_on_the_thread(
    thread: tuple[UUID, UUID],
    open_analysis: Callable[..., AnalysisStore],
    hermetic_wdk: list[Any],
) -> None:
    """The refreshed payload is read back from the row the commit wrote."""
    del hermetic_wdk
    conversation_id, user_id = thread
    open_analysis()

    async with async_session_factory() as session:
        await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    async with async_session_factory() as session:
        stored = await session.scalar(
            select(ConversationStrategy.strategy_ast).where(
                ConversationStrategy.conversation_id == conversation_id
            )
        )
    assert stored is not None
    assert SUBSET_QUERY in json.dumps(stored)


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
        session.add(Conversation(id=conversation_id, user_id=user_id))
        await session.commit()

    async with async_session_factory() as session:
        with pytest.raises(binding.NoOpenAnalysisError) as excinfo:
            await export_analysis_step(
                session=session,
                conversation_id=conversation_id,
                user_id=user_id,
            )
    assert excinfo.value.status == 409


async def test_the_mutated_state_counts_the_write_and_names_the_study(
    thread: tuple[UUID, UUID],
    open_analysis: Callable[..., AnalysisStore],
) -> None:
    """Two surfaces edit one analysis, so each answer says which write it is."""
    conversation_id, _user_id = thread
    open_analysis()

    first = await mutated_analysis_state(conversation_id=conversation_id)
    second = await mutated_analysis_state(conversation_id=conversation_id)

    assert first.revision == 1
    assert second.revision == 2
    assert first.dataset_id == _DATASET
    assert first.study_id == _STUDY
    assert first.analysis_id == _ANALYSIS
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
    open_analysis: Callable[..., AnalysisStore],
    hermetic_wdk: list[Any],
) -> None:
    """A thread that already holds a strategy gains a SECOND root.

    The step is a new root beside the existing one, so the commit's pushable
    branch is still the old root and the EDA step does not reach WDK here.
    """
    conversation_id, user_id = thread
    open_analysis()

    async with async_session_factory() as session:
        await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    ast = await _persisted_ast(conversation_id)
    assert ast.root.search_name == "GenesByTaxon"
    assert [root.search_name for root in ast.detached_roots] == [SUBSET_QUERY]

    pushed = hermetic_wdk[-1]
    assert _search_names(pushed) == ["GenesByTaxon"]


async def _thread_without_a_strategy(*, with_empty_row: bool) -> tuple[UUID, UUID]:
    """A bound thread whose strategy was never built."""
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(Conversation(id=conversation_id, user_id=user_id))
        await session.flush()
        if with_empty_row:
            session.add(ConversationStrategy(conversation_id=conversation_id))
        await session.commit()
    await binding.bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=_ANALYSIS,
    )
    return conversation_id, user_id


@pytest.mark.parametrize("with_empty_row", [False, True])
async def test_an_export_on_a_thread_with_no_strategy_begins_it(
    patch_app_db_engine: None,
    db_cleaner: None,
    open_analysis: Callable[..., AnalysisStore],
    hermetic_wdk: list[Any],
    with_empty_row: bool,
) -> None:
    """The export is the thread's first step, so it becomes the root and is pushed."""
    del patch_app_db_engine, db_cleaner
    conversation_id, user_id = await _thread_without_a_strategy(
        with_empty_row=with_empty_row
    )
    open_analysis()

    async with async_session_factory() as session:
        refreshed = await export_analysis_step(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    ast = await _persisted_ast(conversation_id)
    assert ast.root.search_name == SUBSET_QUERY
    assert ast.detached_roots == []
    assert _search_names(hermetic_wdk[-1]) == [SUBSET_QUERY]
    assert refreshed["rootStepId"] == ast.root.id
    assert [step["searchName"] for step in refreshed["steps"]] == [SUBSET_QUERY]
