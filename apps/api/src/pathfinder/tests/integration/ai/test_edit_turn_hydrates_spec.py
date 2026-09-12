"""A thread whose strategy outlived its spec describes itself from the AST.

The graph editor writes ``conversation_strategies.strategy_ast`` over HTTP and
never touches the checkpoint, so a real strategy can reach a turn with no spec.
The pre-turn hook reconstructs one from what Postgres holds, without WDK.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue, NumberValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import (
    ConversationStrategy,
    PersistedStrategyGraph,
    User,
)
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.tests._support.database import no_database


class _RefusingStrategyApi:
    """A WDK client that fails the test if the pre-turn hook reads from it."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> object:
        self.calls += 1
        msg = f"the pre-turn hook read WDK strategy {strategy_id}"
        raise AssertionError(msg)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


PERCENTILE_SEARCH = (
    "GenesByRNASeqpfal3D7_Josling_Schizont_Transcriptomes_ebi_rnaSeq_RSRCPercentile"
)


def _ast() -> StrategyAst:
    root = StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_taxon",
            search_name="GenesByTaxon",
            parameters={"organism": MultiPickValue(values=["Plasmodium"])},
            display_name="Plasmodium genes",
        ),
        secondary_input=StrategyStepNode(
            id="step_expr",
            search_name=PERCENTILE_SEARCH,
            parameters={"min_expression_percentile": NumberValue(value=90)},
            display_name="top decile expression",
        ),
    )
    return StrategyAst(record_type="transcript", root=root, name="kinase hunt")


async def _seed(db_session: AsyncSession) -> UUID:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    conv_id = uuid4()
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conv_id,
            user_id=user.id,
            site_id="plasmodb",
            name="c",
        )
    )
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv_id,
            strategy_ast=_ast().model_dump(
                by_alias=True, exclude_none=True, mode="json"
            ),
            wdk_strategy_id=None,
            step_count=3,
        )
    )
    await db_session.commit()
    return conv_id


async def _session_from_postgres(
    conv_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> StrategySession:
    """Hydrate the strategy session the way a turn does, from the row."""
    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_strategy(conv_id)
    return build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id=str(conv_id),
            name="c",
            strategy_ast=StrategyAst.model_validate(stored.strategy_ast),
            wdk_strategy_id=stored.wdk_strategy_id,
        ),
    )


def _context(session: StrategySession) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=session,
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


def _state(spec: OperationalSpec | None) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="change the organism to P. vivax",
        domain=StrategyDomainState(operational_spec=spec),
    )


@pytest.fixture
def refusing_api(monkeypatch: Any) -> _RefusingStrategyApi:
    api = _RefusingStrategyApi()
    monkeypatch.setattr(
        "pathfinder.services.strategies.live_counts.get_strategy_api",
        lambda site_id: api,
    )
    return api


async def test_pre_turn_hydrates_when_the_spec_is_missing(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    refusing_api: _RefusingStrategyApi,
) -> None:
    conv_id = await _seed(db_session)
    session = await _session_from_postgres(conv_id, session_maker)

    refreshed = await refresh_live_strategy_state(_state(None), _context(session))

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {"step_taxon", "step_expr"}
    taxon = next(c for c in spec.criteria if c.id == "step_taxon")
    assert taxon.resolved_params["organism"] == MultiPickValue(values=["Plasmodium"])
    assert refusing_api.calls == 0


async def test_the_hydrated_spec_keeps_the_persisted_percentile(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    refusing_api: _RefusingStrategyApi,
) -> None:
    conv_id = await _seed(db_session)
    session = await _session_from_postgres(conv_id, session_maker)

    refreshed = await refresh_live_strategy_state(_state(None), _context(session))

    spec = refreshed.domain.operational_spec
    assert spec is not None
    expr = next(c for c in spec.criteria if c.id == "step_expr")
    assert expr.resolved_params["min_expression_percentile"] == NumberValue(value=90)
    assert refusing_api.calls == 0


async def test_pre_turn_does_not_overwrite_a_real_spec(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    refusing_api: _RefusingStrategyApi,
) -> None:
    conv_id = await _seed(db_session)
    session = await _session_from_postgres(conv_id, session_maker)
    framed = OperationalSpec(
        goal="the framed goal",
        criteria=[Criterion(id="c1", text="framed", search_name="GenesByText")],
    )

    refreshed = await refresh_live_strategy_state(_state(framed), _context(session))

    assert refreshed.domain.operational_spec == framed
    assert refusing_api.calls == 0


async def test_an_empty_graph_leaves_the_spec_alone(
    refusing_api: _RefusingStrategyApi,
) -> None:
    session = StrategySession(site_id="plasmodb")

    refreshed = await refresh_live_strategy_state(_state(None), _context(session))

    assert refreshed.domain.operational_spec is None
    assert refusing_api.calls == 0


async def test_the_entry_spec_is_recorded_for_the_turn(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    refusing_api: _RefusingStrategyApi,
) -> None:
    conv_id = await _seed(db_session)
    session = await _session_from_postgres(conv_id, session_maker)

    refreshed = await refresh_live_strategy_state(_state(None), _context(session))

    before = refreshed.domain.spec_before_turn
    assert before is not None
    assert {c.id for c in before.criteria} == {"step_taxon", "step_expr"}
    assert before is not refreshed.domain.operational_spec


async def test_an_approval_resume_keeps_the_entry_spec_the_turn_recorded(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    refusing_api: _RefusingStrategyApi,
) -> None:
    """The resume continues the turn, so it does not re-record a mid-turn spec."""
    conv_id = await _seed(db_session)
    session = await _session_from_postgres(conv_id, session_maker)
    recorded = OperationalSpec(
        goal="the goal the turn started with",
        criteria=[Criterion(id="c1", text="recorded", search_name="GenesByText")],
    )
    state = _state(None)
    state.domain.spec_before_turn = recorded
    state.pending_approval = PendingApproval(
        phase="frame", tool_call_id="call_1", tool_name="frame_problem"
    )

    refreshed = await refresh_live_strategy_state(state, _context(session))

    assert refreshed.domain.spec_before_turn == recorded
    assert refusing_api.calls == 0
