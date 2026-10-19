"""A canvas save reads each search definition once, and the next save reads it again."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import VEuPathDBClient

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests.integration.http.conftest import (
    first_frame_client_for,
    make_user,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("open_job_queue"),
    pytest.mark.skipif(
        needs_qa_recording("wdk/search_genes_by_molecular_weight.json"),
        reason=NEEDS_QA_RECORDING,
    ),
]

SEARCH = "GenesByMolecularWeight"


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Each push reads the search definition twice, as a step write does."""
    seen: list[str | None] = []
    site = VEuPathDBClient("https://qa.plasmodb.org/plasmo.qa/service")

    async def get(path: str, **_: object) -> JsonValue:
        del path
        seen.append(veupathdb_auth_token_ctx.get())
        return load_recorded("search_genes_by_molecular_weight").json_body()

    async def push_reading_twice(**pushed: Any) -> _WDKCommitOutcome:
        del pushed
        for _ in range(2):
            await site.get_search_details("transcript", SEARCH)
        return _WDKCommitOutcome(succeeded_step_ids=[], failures=[], sync_result=None)

    monkeypatch.setattr(site, "get", get)
    monkeypatch.setattr(commit, "_commit_to_wdk", push_reading_twice)
    return seen


@pytest.fixture
async def thread(
    app: FastAPI,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[tuple[httpx.AsyncClient, UUID]]:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    async with session_maker() as session:
        user = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
        )
        session.add(conversation)
        await session.commit()
    async with first_frame_client_for(app, user.id, wdk_token="ada-token") as client:
        yield client, conversation.id


async def _add_leaf(
    client: httpx.AsyncClient, conversation_id: UUID, step: str
) -> None:
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/operations?siteId=plasmodb",
        json={
            "op": {
                "kind": "addLeaf",
                "step": {"id": step, "searchName": "GenesByTaxon"},
                "attach": {"mode": "new-root"},
            },
        },
    )
    assert response.status_code == 200, response.text


async def test_one_canvas_save_reads_a_definition_once(
    thread: tuple[httpx.AsyncClient, UUID], reads: list[str | None]
) -> None:
    client, conversation_id = thread

    await _add_leaf(client, conversation_id, "s1")

    assert reads == ["ada-token"]


async def test_the_next_canvas_save_reads_it_again(
    thread: tuple[httpx.AsyncClient, UUID], reads: list[str | None]
) -> None:
    client, conversation_id = thread

    await _add_leaf(client, conversation_id, "s1")
    await _add_leaf(client, conversation_id, "s2")

    assert reads == ["ada-token", "ada-token"]
