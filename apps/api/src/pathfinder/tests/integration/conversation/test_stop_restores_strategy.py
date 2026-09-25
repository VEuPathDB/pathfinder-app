"""Stopping a turn mid-build leaves the strategy the thread had before it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform import db
from sqlalchemy import select

from pathfinder.ai.conversation import turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.plan_validation import validate_plan_or_raise
from pathfinder.tests.integration.persistence._strategy_shapes import (
    four_step_ast,
    three_step_ast,
)

_THREE = {"combine": 15, "protease": 13, "gameto": 14}


@dataclass
class _RuntimeCtx:
    cancel_event: asyncio.Event


class _HalfBuildThenHang:
    """Writes the local plan, then never reaches the WDK push."""

    def __init__(self, conversation_id: UUID, cancel_event: asyncio.Event) -> None:
        self.conversation_id = conversation_id
        self.cancel_event = cancel_event

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: str,
    ) -> AsyncIterator[tuple[str, Any]]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[tuple[str, Any]]:
        await _write_half_built_plan(self.conversation_id)
        self.cancel_event.set()
        await asyncio.sleep(30)
        yield ("custom", {"type": "data-noop"})


async def _write_half_built_plan(conversation_id: UUID) -> None:
    """The build phase writes the plan before WDK has answered."""
    ast = four_step_ast()
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=ast,
                record_type=None,
                step_count=4,
                wdk_strategy_id=None,
                wdk_strategy_id_set=True,
            ),
        )
        await session.commit()


async def _seed_thread() -> tuple[UUID, UUID]:
    user_id, conversation_id = uuid4(), uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="protease work",
            ),
        )
        await session.commit()
    return user_id, conversation_id


async def _write_three_step_strategy(conversation_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=three_step_ast(dict(_THREE)),
                record_type="transcript",
                step_count=3,
                wdk_strategy_id=330423363,
                wdk_strategy_id_set=True,
            ),
        )
        await session.commit()


def _body(conversation_id: UUID) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "add the ortholog step"}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


async def _run_stopped_turn(
    conversation_id: UUID,
    user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_poll(**_kwargs: Any) -> None:
        return None

    async def _no_title(*_args: Any, **_kwargs: Any) -> str:
        return ""

    monkeypatch.setattr(turn_runner, "watch_for_cancel", _no_poll)
    monkeypatch.setattr(turn_runner, "charged_conversation_title", _no_title)
    cancel_event = asyncio.Event()
    await turn_runner._run_turn_with_context(
        request=turn_runner.TurnRequest(body=_body(conversation_id), user_id=user_id),
        spec=build_pathfinder_spec(),
        compiled_graph=_HalfBuildThenHang(conversation_id, cancel_event),
        runtime_context=_RuntimeCtx(cancel_event=cancel_event),
        writer=ChatEventWriter(conversation_id=conversation_id, turn_id=uuid4()),
    )


async def _chunk_types(conversation_id: UUID) -> list[str]:
    async with db.async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ConversationEvent)
                    .where(ConversationEvent.conversation_id == conversation_id)
                    .order_by(ConversationEvent.id),
                )
            )
            .scalars()
            .all()
        )
    return [str(row.chunk.get("type")) for row in rows]


async def test_stop_mid_build_puts_the_previous_strategy_back(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_thread()
    await _write_three_step_strategy(conversation_id)

    await _run_stopped_turn(conversation_id, user_id, monkeypatch)

    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, conversation_id)
        assert strategy is not None
        assert strategy.step_count == 3
        assert strategy.record_type == "transcript"
        assert strategy.wdk_strategy_id == 330423363
    # The card's 422: the editor posts the plan and the validator refuses it.
    validate_plan_or_raise(dict(strategy.strategy_ast))

    types = await _chunk_types(conversation_id)
    assert "data-turn-stopped" in types
    revision_index = types.index("data-strategy-revision")
    assert revision_index == types.index("data-turn-stopped") + 1
    async with db.async_session_factory() as session:
        emitted = (
            (
                await session.execute(
                    select(ConversationEvent)
                    .where(ConversationEvent.conversation_id == conversation_id)
                    .order_by(ConversationEvent.id),
                )
            )
            .scalars()
            .all()
        )[revision_index]
    assert emitted.chunk["data"]["revision"] == strategy_revision(
        three_step_ast(dict(_THREE)),
    )


async def test_stop_mid_first_build_leaves_no_half_written_strategy(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card's repro: a fresh chat stopped while build was `started`."""
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_thread()

    await _run_stopped_turn(conversation_id, user_id, monkeypatch)

    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, conversation_id)
        assert strategy is not None
        assert strategy.strategy_ast == {}
        assert strategy.record_type is None
        assert strategy.step_count == 0
    assert "data-strategy-revision" not in await _chunk_types(conversation_id)
