"""The thread, the analysis document and the recorded push the export tests share."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import SinglePickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.eda import (
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
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.eda import binding
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests._support.eda_wire import (
    AnalysisStore,
    eda_transport,
    wire_eda,
)
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    sample_filter,
)

DATASET = "DS_53f554ec6a"
STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"
ANALYSIS = "t4fszEJ"
ROOT = "root"


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
        analysis_id=ANALYSIS,
        display_name="berghei subset",
        study_id=DATASET,
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


def strategy_ast() -> dict[str, Any]:
    root = StrategyStepNode(
        id=ROOT,
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

    def opened(
        *, with_computation: bool = False, samples_only: bool = False
    ) -> AnalysisStore:
        detail = _detail(with_computation=with_computation)
        if samples_only:
            detail = detail.model_copy(
                update={
                    "descriptor": EdaAnalysisDescriptor(
                        subset=EdaSubsetDescriptor(descriptor=[sample_filter()])
                    )
                }
            )
        store = AnalysisStore(detail=detail)
        fixture = "study_detail_de" if samples_only else "study_detail_phenotype"
        wire_eda(
            monkeypatch,
            eda_transport(study_id=STUDY, study_fixture=fixture, store=store),
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
        return _WDKCommitOutcome(succeeded_step_ids=[], failures=[], sync_result=None)

    monkeypatch.setattr(commit, "_commit_to_wdk", no_push)
    return pushed


@pytest.fixture
async def thread(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> tuple[UUID, UUID]:
    """A user, a conversation holding one step, and an analysis bound to it."""
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
        await session.flush()
        session.add(
            ConversationStrategy(
                conversation_id=conversation_id,
                strategy_ast=strategy_ast(),
            )
        )
        await session.commit()
    await binding.bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=DATASET,
        analysis_id=ANALYSIS,
    )
    return conversation_id, user_id


def _walk(node: StrategyStepNode) -> Iterator[StrategyStepNode]:
    yield node
    for child in (node.primary_input, node.secondary_input):
        if child is not None:
            yield from _walk(child)


def search_names(ast: StrategyAst) -> list[str]:
    """Every search the AST names, across its root and its detached roots."""
    return [
        node.search_name
        for root in (ast.root, *ast.detached_roots)
        for node in _walk(root)
    ]


async def persisted_ast(conversation_id: UUID) -> StrategyAst:
    """The strategy the thread now holds, read back from its row."""
    async with async_session_factory() as session:
        stored = await session.scalar(
            select(ConversationStrategy.strategy_ast).where(
                ConversationStrategy.conversation_id == conversation_id
            )
        )
    assert stored is not None
    return StrategyAst.model_validate(stored)


async def added_step(conversation_id: UUID) -> StrategyStepNode:
    """The EDA-backed leaf the export added to the thread's strategy."""
    ast = await persisted_ast(conversation_id)
    roots = [ast.root, *ast.detached_roots]
    return next(
        node
        for root in roots
        for node in _walk(root)
        if node.search_name in {SUBSET_QUERY, COMPUTE_QUERY}
    )
