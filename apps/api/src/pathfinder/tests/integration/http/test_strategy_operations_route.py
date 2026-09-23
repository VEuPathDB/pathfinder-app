"""The graph canvas's one-operation endpoint, on a thread with no strategy yet."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

pytestmark = pytest.mark.asyncio

_CORRUPT_AST: dict[str, Any] = {"root": "not-a-node"}


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
async def fresh_thread(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[tuple[httpx.AsyncClient, UUID]]:
    """A thread with no strategy row at all."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        user = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
        )
        session.add(conversation)
        await session.commit()
    client = first_frame_client_for(app, user.id, wdk_token="test-token")
    async with client:
        yield client, conversation.id


async def test_a_new_root_on_a_thread_with_no_strategy_begins_it(
    fresh_thread: tuple[httpx.AsyncClient, UUID],
    hermetic_wdk: list[Any],
) -> None:
    """The first leaf a thread receives becomes its root."""
    client, conversation_id = fresh_thread
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/operations?siteId=plasmodb",
        json={
            "op": {
                "kind": "addLeaf",
                "step": {"id": "s1", "searchName": "GenesByTaxon"},
                "attach": {"mode": "new-root"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rootStepId"] == "s1"
    assert [step["searchName"] for step in body["steps"]] == ["GenesByTaxon"]
    assert hermetic_wdk


async def test_deleting_a_step_on_a_thread_with_no_strategy_names_the_step(
    fresh_thread: tuple[httpx.AsyncClient, UUID],
    hermetic_wdk: list[Any],
) -> None:
    """An operation that needs a graph is refused by the op algebra itself."""
    del hermetic_wdk
    client, conversation_id = fresh_thread
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/operations?siteId=plasmodb",
        json={
            "op": {
                "kind": "deleteStep",
                "stepId": "s1",
                "resolution": "delete-subtree",
            },
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["title"] == "the strategy cannot place this delete"
    assert body["detail"] == "s1 is not a step of this strategy"


async def test_a_corrupt_stored_ast_is_refused_and_the_row_is_left_alone(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
    hermetic_wdk: list[Any],
) -> None:
    """A stored AST that does not parse is corruption, not an empty strategy."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        user = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
        )
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationStrategy(
                conversation_id=conversation.id,
                strategy_ast=_CORRUPT_AST,
            )
        )
        await session.commit()

    async with first_frame_client_for(app, user.id, wdk_token="t") as client:
        response = await client.post(
            f"/api/v1/conversations/{conversation.id}/operations?siteId=plasmodb",
            json={
                "op": {
                    "kind": "addLeaf",
                    "step": {"id": "s1", "searchName": "GenesByTaxon"},
                    "attach": {"mode": "new-root"},
                },
            },
        )

    assert response.status_code == 500
    assert response.json()["code"] == "STRATEGY_AST_CORRUPT"
    assert hermetic_wdk == []
    async with session_maker() as session:
        stored = await session.scalar(
            select(ConversationStrategy.strategy_ast).where(
                ConversationStrategy.conversation_id == conversation.id
            )
        )
    assert stored == _CORRUPT_AST
