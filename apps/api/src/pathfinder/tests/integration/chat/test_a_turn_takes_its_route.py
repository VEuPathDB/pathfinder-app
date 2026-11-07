from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.models.mock.explore_arc import ONE_READING
from pathfinder.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    NO_READING_PROMPT,
    ONE_READING_PROMPT,
    PREFERENCE_PROMPT,
    serve_recorded_readings,
)
from pathfinder.tests.integration.chat._helpers import (
    approval_tool_names,
    approve_card,
    checkpointed,
    post_chat_turn,
    routes,
    run_one_chat_turn,
    turn_modes,
    types,
)

ECHO_PROMPT = "Show me the current strategy. [[arc:echo]]"

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "app_memory_store"
)


@pytest.fixture(autouse=True)
def recorded_readings(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_readings(monkeypatch)


async def test_an_explore_turn_in_auto_is_marked_and_offers_its_card(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=EXPLORE_PROMPT,
        conversation_id=cid,
    )
    assert routes(chunks) == ["explore"]
    assert approval_tool_names(chunks) == ["consult_user"]
    assert await turn_modes(cid) == [("user", "auto"), ("assistant", "explore")]
    assert "data-graph-snapshot" not in types(chunks)


async def _preference_card(
    app: FastAPI, user_id: UUID, connector: InMemoryConnector, cid: UUID
) -> list[dict[str, Any]]:
    asked = await run_one_chat_turn(
        app=app,
        user_id=user_id,
        connector=connector,
        prompt=PREFERENCE_PROMPT,
        conversation_id=cid,
        mode="explore",
    )
    assert approval_tool_names(asked) == ["remember"]
    return asked


async def test_a_typed_message_over_an_explore_card_follows_build_mode(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    await _preference_card(app, authed_user_id, in_memory_jobs, cid)
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=ECHO_PROMPT,
        conversation_id=cid,
        mode="build",
    )
    assert routes(chunks) == ["build"]
    assert (await turn_modes(cid))[-1] == ("assistant", "build")
    assert [(await checkpointed(cid)).pending_approval] == [None]


async def test_a_typed_message_over_an_explore_card_in_explore_mode_starts_fresh(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    await _preference_card(app, authed_user_id, in_memory_jobs, cid)
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=NO_READING_PROMPT,
        conversation_id=cid,
        mode="explore",
    )
    assert (routes(chunks), approval_tool_names(chunks)) == (["explore"], [])
    assert (await turn_modes(cid))[-1] == ("assistant", "explore")
    assert [(await checkpointed(cid)).pending_approval] == [None]


async def test_an_answered_explore_card_resumes_explore(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    asked = await _preference_card(app, authed_user_id, in_memory_jobs, cid)
    chunks = await post_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        body=approve_card(cid, asked, mode="build"),
    )
    assert (routes(chunks), approval_tool_names(chunks)) == (
        ["explore"],
        ["consult_user"],
    )
    assert (await turn_modes(cid))[-1] == ("assistant", "explore")


async def test_one_buildable_reading_ends_on_words_that_name_build(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=ONE_READING_PROMPT,
        conversation_id=cid,
    )
    said = "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta")
    assert (routes(chunks), approval_tool_names(chunks)) == (["explore"], [])
    assert said == ONE_READING
    assert [(await checkpointed(cid)).pending_approval] == [None]


async def test_existing_build_arcs_route_to_build_in_auto(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=ECHO_PROMPT,
    )
    assert routes(chunks) == ["build"]


async def test_an_auto_thread_routes_each_message_again(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    explored = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=NO_READING_PROMPT,
        conversation_id=cid,
    )
    built = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=ECHO_PROMPT,
        conversation_id=cid,
    )
    assert (routes(explored), routes(built)) == (["explore"], ["build"])
    assert await turn_modes(cid) == [
        ("user", "auto"),
        ("assistant", "explore"),
        ("user", "auto"),
        ("assistant", "build"),
    ]
