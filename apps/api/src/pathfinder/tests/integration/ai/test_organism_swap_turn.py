"""The acceptance turn: swap the organism on one criterion, keep the rest.

FRAME re-binds only the criterion the request names, through the real parameter
resolver, and the edit reaches WDK as one step patch. The two criteria the
request never mentions come out byte for byte identical.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult, set_criterion
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.integration.ai._organism_swap_wire import (
    DERISI,
    PF,
    PV,
    WDK_IDS,
    ZHU,
    RecordingAPI,
    wdk,
)

__all__ = ["wdk"]


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


def _root() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_c2",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_c1",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=StrategyStepNode(
                id="step_text",
                search_name="GenesByText",
                display_name="protease text",
                parameters={
                    "text_expression": SinglePickValue(value="protease"),
                    "organism": MultiPickValue(values=["Plasmodium"]),
                },
            ),
            secondary_input=StrategyStepNode(
                id="step_go",
                search_name="GenesByGoTerm",
                display_name="proteolysis GO",
                parameters={
                    "go_term": SinglePickValue(value="GO:0006508"),
                    "organism": MultiPickValue(values=["Plasmodium"]),
                },
            ),
        ),
        secondary_input=StrategyStepNode(
            id="step_expr",
            search_name="GenesByProfile",
            display_name="expression profile",
            parameters={
                "organism": MultiPickValue(values=[PF]),
                "profileset": SinglePickValue(value=DERISI),
            },
        ),
    )


def _before() -> OperationalSpec:
    return spec_from_ast(
        StrategyAst(record_type="transcript", root=_root()),
        goal="proteases with an expression profile",
    )


async def _seed(db_session: AsyncSession, user: User) -> UUID:
    ast = StrategyAst(
        record_type="transcript", root=_root(), wdk_step_ids=dict(WDK_IDS)
    )
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Test strategy",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=777,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
    )
    await db_session.commit()
    return conv.id


def _deps(conv_id: UUID, session_maker: Any) -> LeadDeps:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conv_id), name="Test strategy", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_root())
    graph.recompute_roots()
    graph.last_step_id = "step_c2"
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(WDK_IDS), wdk_strategy_id=777, step_counts={}
    )
    before = _before()
    state = PipelineState(
        conversation_id=conv_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="use P. vivax P01 for the expression profile, keep the rest",
        domain=StrategyDomainState(
            operational_spec=before.model_copy(deep=True),
            spec_before_turn=before.model_copy(deep=True),
        ),
    )
    runtime = Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=session,
        db_session_factory=session_maker,
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])


def _frame_that_swaps_the_organism(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """FRAME re-binds only the expression criterion, through the real resolver."""
    rounds: list[str] = []

    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        ctx: RunContext[AgentDeps] = RunContext(
            deps=agent_deps,
            model=TestModel(),
            usage=RunUsage(),
            messages=[],
            tool_call_id="call_1",
        )
        first = returned(
            await set_criterion(
                ctx,
                criterion_id="step_expr",
                text="expression profile",
                search_name="GenesByProfile",
                params={"organism": [PV], "profileset": DERISI},
            ),
            SetCriterionResult,
        )
        rounds.extend(first.redecide)
        await set_criterion(
            ctx,
            criterion_id="step_expr",
            text="expression profile",
            search_name="GenesByProfile",
            params={"organism": [PV], "profileset": ZHU},
        )
        return FrameResult(
            disposition="spec_ready",
            summary="expression profile moved to P. vivax P01",
            changes=[
                CriterionChange(criterion_id="step_text", disposition="kept"),
                CriterionChange(criterion_id="step_go", disposition="kept"),
                CriterionChange(
                    criterion_id="step_expr",
                    disposition="changed",
                    changed_params={"organism": f'["{PV}"]', "profileset": ZHU},
                ),
            ],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    return rounds


async def test_the_swap_re_resolves_the_dependent_and_keeps_the_rest(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    wdk: RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    before = _before()
    redecided = _frame_that_swaps_the_organism(monkeypatch)

    result = await run_edit(
        deps=deps, parent_tool_call_id="t1", reason="swap the profile organism"
    )

    assert isinstance(result, EditDelta)
    # The dependent was handed back rather than copied forward.
    assert redecided == ["profileset"]
    after = deps.state.domain.operational_spec
    assert after is not None
    swapped = next(c for c in after.criteria if c.id == "step_expr")
    assert swapped.resolved_params["organism"] == MultiPickValue(values=[PV])
    assert swapped.resolved_params["profileset"] == SinglePickValue(value=ZHU)
    # Every criterion the request never named is byte for byte what it was.
    for criterion_id in ("step_text", "step_go"):
        was = next(c for c in before.criteria if c.id == criterion_id)
        now = next(c for c in after.criteria if c.id == criterion_id)
        assert now.resolved_params == was.resolved_params
        assert now.search_name == was.search_name


async def test_the_swap_patches_one_step_and_keeps_every_wdk_id(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    wdk: RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    _frame_that_swaps_the_organism(monkeypatch)

    result = await run_edit(
        deps=deps, parent_tool_call_id="t1", reason="swap the profile organism"
    )

    assert isinstance(result, EditDelta)
    assert [c.kwargs["step_id"] for c in wdk.named("update_step_search_config")] == [
        400
    ]
    assert wdk.named("delete_step") == []
    sync_state = deps.runtime.strategy_session.sync_state
    assert sync_state is not None
    assert sync_state.wdk_step_ids == WDK_IDS
    assert result.diff.render() == "kept 2, changed 1, added 0, dropped 0"
    assert sorted(result.preserved_step_ids) == ["step_go", "step_text"]
