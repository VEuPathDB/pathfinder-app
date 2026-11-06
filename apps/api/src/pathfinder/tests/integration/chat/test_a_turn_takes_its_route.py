from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.tests.integration.chat._helpers import (
    approval_tool_names,
    routes,
    run_one_chat_turn,
    tool_names,
    turn_modes,
    types,
)
from pathfinder.tests.unit.ai.graph._explore_turns import (
    EXPLORE_PROMPT,
    NO_READING_PROMPT,
    PREFERENCE_PROMPT,
    serve_recorded_readings,
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


async def test_a_typed_message_over_an_explore_preference_card_goes_to_explore(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    asked = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=PREFERENCE_PROMPT,
        conversation_id=cid,
        mode="explore",
    )
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=ECHO_PROMPT,
        conversation_id=cid,
        mode="build",
    )
    assert approval_tool_names(asked) == ["remember"]
    assert (routes(chunks), tool_names(chunks)) == ([], [])
    assert (await turn_modes(cid))[-1] == ("assistant", "explore")


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
