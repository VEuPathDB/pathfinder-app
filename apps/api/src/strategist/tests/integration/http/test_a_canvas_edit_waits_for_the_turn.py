from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode, walk

from strategist.domain.strategy.operations import (
    GraphOperation,
    UpdateCombineOperatorOp,
)
from strategist.jobs.app import procrastinate_app
from strategist.persistence.models import ConversationStrategy
from strategist.persistence.repositories.conversation import ConversationRepository
from strategist.platform.config import get_settings
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.services.conversations import strategy_ops
from strategist.services.conversations.thread_lock import (
    hold_thread,
    try_lock_thread,
)
from strategist.services.strategies import commit
from strategist.services.strategies.commit import (
    _WDKCommitOutcome,
    apply_operations_and_commit,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.session_factory import (
    build_strategy_session,
    persisted_graph,
)
from strategist.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)
from strategist.tests.integration.persistence._busy_thread import (
    PROPOSAL,
    make_busy,
    put_pending_approval,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("open_job_queue")]

SITE = "plasmodb"
CANVAS_NAME = "Named on the canvas"
REFUSALS = {
    "queued turn": (
        "This chat is still answering. Make this edit once the reply has finished."
    ),
    "running turn": (
        "This chat is still answering. Make this edit once the reply has finished."
    ),
    "active task": (
        "This chat is running a background task. "
        "Make this edit once the task has finished."
    ),
}
TURNS = {"queued turn", "running turn"}
WHILE_LOCKED = "This chat is changing right now. Try the edit again in a moment."
RENAME_ON_THE_CANVAS = {
    "op": {
        "kind": "updateStepMeta",
        "stepId": "step_text",
        "displayName": CANVAS_NAME,
    },
}
TURN_EDIT = UpdateCombineOperatorOp(
    step_id="step_combine", operator=CombineOp.INTERSECT
)


@dataclass
class _SitePush:
    hold: bool = False
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def __call__(self, **_kwargs: Any) -> _WDKCommitOutcome:
        if self.hold:
            self.entered.set()
            await self.release.wait()
        return _WDKCommitOutcome(succeeded_step_ids=[], failures=[], sync_result=None)


@dataclass(frozen=True)
class _Thread:
    client: httpx.AsyncClient
    conversation_id: UUID
    user_id: UUID

    async def send_edit(
        self, body: dict[str, Any] = RENAME_ON_THE_CANVAS
    ) -> httpx.Response:
        return await self.client.post(
            f"/api/v1/conversations/{self.conversation_id}/operations?siteId={SITE}",
            json=body,
        )

    async def insert_saved(self) -> httpx.Response:
        return await self.client.post(
            f"/api/v1/conversations/{self.conversation_id}/insert-saved?siteId={SITE}",
            json={"targetStepId": "step_text", "savedWdkStrategyId": 7777},
        )

    async def stored(self) -> StrategyAst:
        async with db.async_session_factory() as session:
            row = await ConversationRepository(session).get_strategy(
                self.conversation_id
            )
        return StrategyAst.model_validate(row.strategy_ast)

    async def canvas_name(self) -> str | None:
        stored = await self.stored()
        return next(n for n in walk(stored.root) if n.id == "step_text").display_name

    async def is_unclaimed(self) -> bool:
        async with db.async_session_factory() as session:
            thread_free = await try_lock_thread(session, self.conversation_id)
            strategy_free = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:k, 0))"),
                {"k": f"strategy:{self.conversation_id}"},
            )
        return thread_free and bool(strategy_free)


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes, procrastinate_jobs CASCADE",
            ),
        )
        await session.commit()


@pytest.fixture
def site_push(
    monkeypatch: pytest.MonkeyPatch, saver: AsyncPostgresSaver
) -> Iterator[_SitePush]:
    del saver
    push = _SitePush()
    monkeypatch.setattr(commit, "_commit_to_wdk", push)
    yield push
    push.release.set()


@pytest.fixture
async def thread(
    app: FastAPI,
    db_cleaner: None,
    signed_in_to_veupathdb: None,
    site_push: _SitePush,
    saver: AsyncPostgresSaver,
) -> AsyncIterator[_Thread]:
    del db_cleaner, signed_in_to_veupathdb, site_push, saver
    tree = StrategyStepNode(
        id="step_combine",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value="kinase")},
        ),
        secondary_input=StrategyStepNode(
            id="step_go",
            search_name="GenesByGoTerm",
            parameters={"go_term": StringValue(value="GO:0004672")},
        ),
    )
    async with db.async_session_factory() as session:
        user = await make_user(session)
        conversation = Conversation(
            assistant_id=STRATEGIST_ASSISTANT_ID,
            id=uuid4(),
            user_id=user.id,
            site_id=SITE,
            name="Kinase strategy",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationStrategy(
                conversation_id=conversation.id,
                strategy_ast=StrategyAst(
                    record_type="transcript", root=tree
                ).model_dump(by_alias=True, exclude_none=True, mode="json"),
            ),
        )
        await session.commit()
    async with first_frame_client_for(app, user.id, wdk_token="test-token") as client:
        yield _Thread(client, conversation.id, user.id)


async def _make_busy(
    kind: str, thread: _Thread, saver: AsyncPostgresSaver
) -> Callable[[], Awaitable[None]]:
    clear = await make_busy(
        kind,
        saver=saver,
        conversation_id=thread.conversation_id,
        user_id=thread.user_id,
    )
    if kind in TURNS:
        await procrastinate_app.open_async()
    return clear


async def _turn_context(thread: _Thread) -> StrategyMutationContext:
    async with db.async_session_factory() as session:
        found = await ConversationRepository(session).get_with_strategy(
            thread.conversation_id
        )
    assert found is not None
    return StrategyMutationContext(
        site_id=SITE,
        strategy_session=build_strategy_session(
            site_id=SITE, strategy_graph=persisted_graph(*found)
        ),
        conversation_id=thread.conversation_id,
        db_session_factory=db.async_session_factory,
    )


async def test_an_edit_during_a_running_turn_is_refused_and_the_turn_keeps_its_edit(
    thread: _Thread, saver: AsyncPostgresSaver
) -> None:
    clear = await _make_busy("running turn", thread, saver)
    turn = await _turn_context(thread)

    response = await thread.send_edit()
    await apply_operations_and_commit(deps=turn, ops=[TURN_EDIT])

    stored = await thread.stored()
    assert (response.status_code, stored.root.operator, await thread.canvas_name()) == (
        409,
        CombineOp.INTERSECT,
        None,
    )
    assert response.json()["code"] == "EDIT_REFUSED"
    await clear()
    assert (await thread.send_edit()).status_code == 200
    stored = await thread.stored()
    assert (stored.root.operator, await thread.canvas_name()) == (
        CombineOp.INTERSECT,
        CANVAS_NAME,
    )


@pytest.mark.parametrize("kind", sorted(REFUSALS))
async def test_a_refused_edit_changes_nothing_and_leaves_nothing_claimed(
    kind: str, thread: _Thread, saver: AsyncPostgresSaver
) -> None:
    clear = await _make_busy(kind, thread, saver)

    response = await thread.send_edit()

    assert (response.status_code, response.json()["detail"]) == (409, REFUSALS[kind])
    assert await thread.canvas_name() is None
    assert await thread.is_unclaimed()
    await clear()
    assert (await thread.send_edit()).status_code == 200
    assert await thread.canvas_name() == CANVAS_NAME


async def test_a_refused_edit_saves_no_dataset_on_the_site(
    thread: _Thread,
    saver: AsyncPostgresSaver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[GraphOperation] = []

    async def _save(_site_id: str, op: GraphOperation) -> GraphOperation:
        saved.append(op)
        return op

    monkeypatch.setattr(strategy_ops, "save_dataset_sources", _save)
    clear = await _make_busy("running turn", thread, saver)

    assert (await thread.send_edit()).status_code == 409
    assert saved == []
    await clear()
    assert (await thread.send_edit()).status_code == 200
    assert len(saved) == 1


async def test_an_edit_on_an_idle_thread_applies_and_leaves_nothing_claimed(
    thread: _Thread,
) -> None:
    response = await thread.send_edit()

    assert response.status_code == 200
    assert await thread.canvas_name() == CANVAS_NAME
    assert await thread.is_unclaimed()


async def test_the_thread_stays_claimed_while_an_edit_is_pushed(
    thread: _Thread, site_push: _SitePush
) -> None:
    site_push.hold = True
    edit = asyncio.create_task(thread.send_edit())
    await site_push.entered.wait()

    async with db.async_session_factory() as session:
        assert not await try_lock_thread(session, thread.conversation_id)

    site_push.release.set()
    assert (await edit).status_code == 200
    assert await thread.is_unclaimed()


async def test_two_edits_wait_for_each_other_and_both_apply(
    thread: _Thread, site_push: _SitePush
) -> None:
    site_push.hold = True
    first = asyncio.create_task(thread.send_edit())
    await site_push.entered.wait()
    second = asyncio.create_task(
        thread.send_edit(
            {
                "op": {
                    "kind": "updateCombineOperator",
                    "stepId": "step_combine",
                    "operator": "INTERSECT",
                },
            },
        ),
    )
    await asyncio.sleep(0.2)
    assert not second.done()

    site_push.release.set()
    assert [(await first).status_code, (await second).status_code] == [200, 200]
    stored = await thread.stored()
    assert (stored.root.operator, await thread.canvas_name()) == (
        CombineOp.INTERSECT,
        CANVAS_NAME,
    )


async def test_an_edit_while_the_thread_is_locked_is_refused(thread: _Thread) -> None:
    async with hold_thread(thread.conversation_id):
        response = await thread.send_edit()

    assert (response.status_code, response.json()["detail"]) == (409, WHILE_LOCKED)
    assert await thread.is_unclaimed()
    assert (await thread.send_edit()).status_code == 200


async def test_an_edit_applies_under_a_parked_approval_and_the_answer_reads_it(
    thread: _Thread, saver: AsyncPostgresSaver
) -> None:
    await put_pending_approval(saver, thread.conversation_id, PROPOSAL)

    response = await thread.send_edit()
    assert response.status_code == 200

    answer = await _turn_context(thread)
    await apply_operations_and_commit(deps=answer, ops=[TURN_EDIT])
    stored = await thread.stored()
    assert (stored.root.operator, await thread.canvas_name()) == (
        CombineOp.INTERSECT,
        CANVAS_NAME,
    )


async def test_an_active_task_refuses_the_edit_under_a_parked_approval(
    thread: _Thread, saver: AsyncPostgresSaver
) -> None:
    await put_pending_approval(saver, thread.conversation_id, PROPOSAL)
    await _make_busy("active task", thread, saver)

    response = await thread.send_edit()

    assert (response.status_code, response.json()["detail"]) == (
        409,
        REFUSALS["active task"],
    )


async def test_an_insert_during_a_running_turn_reads_nothing_and_is_refused(
    thread: _Thread,
    saver: AsyncPostgresSaver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    async def _insert(**_kwargs: Any) -> None:
        called.append("insert")

    monkeypatch.setattr(strategy_ops, "insert_saved_into_conversation", _insert)
    await _make_busy("running turn", thread, saver)

    response = await thread.insert_saved()

    assert (response.status_code, response.json()["detail"]) == (
        409,
        REFUSALS["running turn"],
    )
    assert called == []
    assert await thread.is_unclaimed()
