"""The reason a step runs its search reaches the database and comes back on the
thread's next load, as the canvas is served it."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree

from pathfinder.ai.tools.standalone.graph_helpers import build_step_response
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_rationale import ComparedSearch, SearchRationale
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.schemas import step_response_from_strategy_ast
from pathfinder.services.strategies.session_factory import (
    build_strategy_session,
    persisted_graph,
)

_TAXON = "GenesByTaxon"
_CHOSEN = SearchRationale(
    search_name=_TAXON,
    basis="parameter",
    term="Organism",
    reason="sets Organism to Plasmodium falciparum 3D7",
    similarity=0.71,
    compared=[
        ComparedSearch(
            name="GenesByText", display_name="Gene Text Search", similarity=0.4
        )
    ],
    answered=12,
    query="all P. falciparum 3D7 genes",
    tool_call_id="call_taxon",
)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_a",
        search_name=_TAXON,
        display_name="Organism",
        parameters={"organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])},
    )


async def _thread(db_session: AsyncSession) -> UUID:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    conversation_id = uuid4()
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conversation_id,
            user_id=user.id,
            site_id="plasmodb",
            name="taxon",
        )
    )
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conversation_id,
            strategy_ast=StrategyAst(record_type="transcript", root=_leaf()).model_dump(
                by_alias=True, exclude_none=True, mode="json"
            ),
            step_count=1,
        )
    )
    await db_session.commit()
    return conversation_id


async def test_a_stored_strategy_serves_the_reason_it_was_written_with(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _thread(db_session)
    graph = StrategyGraph(str(conversation_id), "taxon", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(_leaf()))
    graph.recompute_roots()
    graph.note_words(
        StepWords(
            criterion_texts={"step_a": "every P. falciparum 3D7 gene"},
            rationales={"step_a": _CHOSEN},
        )
    )
    session = StrategySession(site_id="plasmodb")
    session.add_graph(graph)

    await persist_strategy_ast_to_conversation(
        deps=StrategyMutationContext(
            site_id="plasmodb",
            strategy_session=session,
            conversation_id=conversation_id,
            db_session_factory=session_maker,
        ),
        graph=graph,
        sync_result=None,
    )

    async with session_maker() as fresh:
        loaded = await ConversationRepository(fresh).get_with_strategy(conversation_id)
    assert loaded is not None
    stored = persisted_graph(*loaded)
    reloaded = build_strategy_session(site_id="plasmodb", strategy_graph=stored)
    assert stored.strategy_ast is not None
    assert reloaded.graph is not None
    served = (
        build_step_response(reloaded.graph, reloaded.graph.steps["step_a"]).rationale,
        step_response_from_strategy_ast(
            stored.strategy_ast, stored.strategy_ast.root
        ).rationale,
    )
    assert served == (_CHOSEN, _CHOSEN)
