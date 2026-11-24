from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.platform.errors import AppError, ErrorCode
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from strategist.tests.unit.ai.lead.conftest import session_with_one_step

_THREAD = UUID("6f1c2e0a-0000-4000-8000-000000000002")


class _Refused(AsyncSession):
    async def __aenter__(self) -> _Refused:
        msg = "the database closed the connection"
        raise OSError(msg)


def _context(session: StrategySession) -> StrategyMutationContext:
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=_THREAD,
        db_session_factory=_Refused,
    )


async def test_a_write_the_database_refused_says_the_strategy_was_not_saved() -> None:
    session = session_with_one_step("plasmodb")
    graph = session.get_graph(None)
    assert graph is not None

    with pytest.raises(AppError) as refused:
        await persist_strategy_ast_to_conversation(
            deps=_context(session), graph=graph, sync_result=None
        )

    assert (refused.value.code, refused.value.detail) == (
        ErrorCode.STRATEGY_NOT_SAVED,
        "The strategy was not saved: the database closed the connection",
    )


async def test_a_clear_the_database_refused_says_the_strategy_was_not_saved() -> None:
    session = StrategySession("plasmodb")
    session.add_graph(StrategyGraph("g1", "empty", "plasmodb"))
    graph = session.get_graph(None)
    assert graph is not None

    with pytest.raises(AppError) as refused:
        await persist_strategy_ast_to_conversation(
            deps=_context(session), graph=graph, sync_result=None
        )

    assert refused.value.detail == (
        "The strategy was not saved: the database closed the connection"
    )
