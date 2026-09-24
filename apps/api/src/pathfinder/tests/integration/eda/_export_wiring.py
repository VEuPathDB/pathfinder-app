"""The thread, the analysis document and the recorded push the export tests share."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import SinglePickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.eda import EdaAnalysisDetail
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.eda import binding
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests._support.eda_step_doubles import DE_DATASET, DE_PERMISSION
from pathfinder.tests._support.eda_wire import (
    DE_STUDY,
    PHENOTYPE_DATASET,
    PHENOTYPE_STUDY,
    AnalysisStore,
    eda_transport,
    fixture,
    wire_eda,
)

ROOT = "root"

# Each recorded study, by the dataset id a binding names.
_STUDIES = {
    PHENOTYPE_DATASET: (PHENOTYPE_STUDY, "study_detail_phenotype"),
    DE_DATASET: (DE_STUDY, "study_detail_de"),
}


def strategy_ast() -> dict[str, Any]:
    root = StrategyStepNode(
        id=ROOT,
        search_name="GenesByTaxon",
        display_name="Taxon",
        parameters={"organism": SinglePickValue(value="Plasmodium falciparum 3D7")},
    )
    ast = StrategyAst(record_type="transcript", root=root)
    return ast.model_dump(by_alias=True, exclude_none=True, mode="json")


def _deployment(dataset_id: str, store: AnalysisStore) -> httpx.MockTransport:
    """The recorded deployment, answering for the study ``dataset_id`` names."""
    study_id, study_fixture = _STUDIES[dataset_id]
    recorded = eda_transport(
        study_id=study_id, study_fixture=study_fixture, store=store
    )
    permissions = fixture("permissions")
    permissions["perDataset"][DE_DATASET] = DE_PERMISSION

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=permissions)
        return recorded.handle_request(request)

    return httpx.MockTransport(handler)


@pytest.fixture
def open_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[UUID, EdaAnalysisDetail], Awaitable[AnalysisStore]]]:
    """Bind one analysis to a thread and serve its own study over the wire."""
    token = veupathdb_auth_token_ctx.set("t")

    async def opened(conversation_id: UUID, detail: EdaAnalysisDetail) -> AnalysisStore:
        store = AnalysisStore(detail=detail)
        wire_eda(monkeypatch, _deployment(detail.study_id, store))
        await binding.bind_conversation_analysis(
            conversation_id=conversation_id,
            site_id="plasmodb",
            dataset_id=detail.study_id,
            analysis_id=detail.analysis_id,
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
    """A user and a conversation holding one step, with no analysis bound yet."""
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
