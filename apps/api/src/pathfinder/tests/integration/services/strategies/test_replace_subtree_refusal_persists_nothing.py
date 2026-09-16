"""A refused subtree write leaves the stored strategy exactly as it was."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    walk,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import TurnMarkers
from pathfinder.ai.tools.standalone.strategy_edits import replace_subtree
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.sync_state import WDKSyncState

_KINASE_CRITERIA = ("step_k1", "step_k2", "step_k3", "step_k4")


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


def _leaf(step_id: str, search_name: str = "GenesByTaxon") -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name)


def _combine(
    step_id: str,
    primary: StrategyStepNode,
    secondary: StrategyStepNode,
    operator: CombineOp = CombineOp.INTERSECT,
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=COMBINE_SEARCH_NAME,
        primary_input=primary,
        secondary_input=secondary,
        operator=operator,
    )


def _kinase_strategy() -> StrategyStepNode:
    """Three UNION branches, an ortholog transform, and three filters."""
    u1 = _combine("step_u1", _leaf("step_k1"), _leaf("step_k2"), CombineOp.UNION)
    u2 = _combine("step_u2", _leaf("step_k3"), _leaf("step_k4"), CombineOp.UNION)
    u3 = _combine("step_u3", _leaf("step_ms"), _leaf("step_derisi"), CombineOp.UNION)
    kinases = _combine("step_c1", u1, u2)
    evidence = _combine("step_c2", kinases, u3)
    orthologs = StrategyStepNode(
        id="step_ortho", search_name="GenesByOrthologs", primary_input=evidence
    )
    profiled = _combine("step_c3", orthologs, _leaf("step_phylo"))
    return _combine("step_c4", profiled, _leaf("step_snp"))


def _placeholder_subtree() -> StrategyStepNode:
    """Four placeholder leaves under three intersects."""
    pair = _combine(
        "step_n1",
        _leaf("step_p1", "__input_step__"),
        _leaf("step_p2", "__input_step__"),
    )
    trio = _combine("step_n2", pair, _leaf("step_p3", "__input_step__"))
    return _combine("step_n3", trio, _leaf("step_p4", "__input_step__"))


def _spec(root: StrategyStepNode) -> OperationalSpec:
    """One criterion per step that runs a search."""
    return OperationalSpec(
        goal="kinases with expression and ortholog evidence",
        criteria=[
            Criterion(
                id=node.id, text=f"criterion {node.id}", search_name=node.search_name
            )
            for node in walk(root)
            if node.search_name != COMBINE_SEARCH_NAME
        ],
    )


async def _seed_conversation(
    db_session: AsyncSession, user: User, root: StrategyStepNode
) -> UUID:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Kinase strategy",
    )
    db_session.add(conv)
    await db_session.flush()
    ast = StrategyAst(record_type="transcript", root=root)
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=555,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        ),
    )
    await db_session.commit()
    return conv.id


def _deps(
    conv_id: UUID,
    root: StrategyStepNode,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AgentDeps:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conv_id), name="Kinase strategy", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_strategy_id=555)
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=conv_id,
        db_session_factory=db_session_factory,
        agent_state=AgentToolState(operational_spec_draft=_spec(root)),
        turn_markers=TurnMarkers(),
    )


def _ctx(deps: AgentDeps) -> RunContext[AgentDeps]:
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage(), messages=[])


async def test_a_refused_replacement_leaves_the_stored_strategy_intact(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
) -> None:
    root = _kinase_strategy()
    conv_id = await _seed_conversation(db_session, seed_user, root)
    deps = _deps(conv_id, root, session_maker)

    with pytest.raises(ModelRetry) as excinfo:
        await replace_subtree(_ctx(deps), "step_c1", _placeholder_subtree())

    for lost in _KINASE_CRITERIA:
        assert lost in str(excinfo.value)
    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_strategy(conv_id)
        ast = StrategyAst.model_validate(stored.strategy_ast)
        step_ids = {node.id for node in walk(ast.root)}
        assert len(step_ids) == 16
        assert set(_KINASE_CRITERIA) <= step_ids
        assert "__input_step__" not in {node.search_name for node in walk(ast.root)}
        by_id = {node.id: node for node in walk(ast.root)}
        assert by_id["step_u1"].operator == CombineOp.UNION
        assert by_id["step_u2"].operator == CombineOp.UNION
        assert by_id["step_c1"].operator == CombineOp.INTERSECT
        assert by_id["step_c1"].primary_input_id == "step_u1"
        assert by_id["step_c1"].secondary_input_id == "step_u2"
        assert by_id["step_ortho"].primary_input_id == "step_c2"
