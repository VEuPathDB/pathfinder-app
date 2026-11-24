from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from veupathdb.domain.strategy import CombineOp, StrategyAst

from strategist.persistence.models import StrategyRevision
from strategist.persistence.repositories.conversation import ConversationRepository
from strategist.persistence.repositories.conversation_update import ConversationUpdate
from strategist.platform.config import get_settings
from strategist.tests.integration.conversation import _turn_harness
from strategist.tests.integration.conversation._turn_harness import (
    FIRST_LABEL,
    Recorder,
    run_turn,
    seed_thread,
    silence_turn_runner,
    spec_for,
)
from strategist.tests.integration.persistence._strategy_shapes import three_step_ast


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened


@pytest.fixture(autouse=True)
def _no_title_and_no_cancel_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    silence_turn_runner(monkeypatch)


def _joined(operator: CombineOp) -> StrategyAst:
    ast = three_step_ast()
    return ast.model_copy(
        update={"root": ast.root.model_copy(update={"operator": operator})}
    )


def _writes_two_trees(conversation_id: UUID) -> object:
    async def record_finding(label: str) -> str:
        for operator in (CombineOp.MINUS, CombineOp.UNION):
            async with db.async_session_factory() as session:
                await ConversationRepository(session).update_conversation(
                    conversation_id,
                    ConversationUpdate(
                        strategy_ast=_joined(operator),
                        record_type="transcript",
                        step_count=3,
                    ),
                )
                await session.commit()
        return f"recorded {label}"

    return record_finding


async def test_every_snapshot_a_turn_writes_carries_the_turn_s_message(
    patch_app_db_engine: None,
    db_cleaner: None,
    saver: AsyncPostgresSaver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await seed_thread()
    monkeypatch.setattr(
        _turn_harness, "record_finding", _writes_two_trees(conversation_id)
    )

    turn = await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec_for(Recorder(), saver),
        saver=saver,
    )

    async with db.async_session_factory() as session:
        named = (
            await session.scalars(
                select(StrategyRevision.message_id)
                .where(StrategyRevision.conversation_id == conversation_id)
                .order_by(StrategyRevision.id)
            )
        ).all()
    assert named == [turn.assistant_message_id, turn.assistant_message_id]
