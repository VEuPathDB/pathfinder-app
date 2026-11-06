from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.tests.integration.chat._helpers import run_one_chat_turn
from pathfinder.tests.integration.chat.conftest import recorded_site_reads
from pathfinder.tests.integration.http._two_assistants import turn_with_body
from pathfinder.tests.integration.http.conftest import client_for

__all__ = ["recorded_site_reads"]

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "app_memory_store"
)

_REMEMBER_PROMPT = (
    "Please remember for future sessions: I always work with P. falciparum 3D7. "
    "[[arc:remember]]"
)


async def _detail(app: FastAPI, user_id: UUID, conversation_id: UUID) -> Any:
    async with client_for(app, user_id) as client:
        return (await client.get(f"/api/v1/conversations/{conversation_id}")).json()


def _approval_body(
    conversation_id: UUID, asked: list[dict[str, Any]], *, mode: str
) -> dict[str, Any]:
    request = next(c for c in asked if c["type"] == "tool-approval-request")
    call = next(
        c
        for c in asked
        if c["type"] == "tool-input-available"
        and c["toolCallId"] == request["toolCallId"]
    )
    message_id = str(uuid4())
    return {
        "trigger": "submit-message",
        "id": message_id,
        "messages": [
            {
                "id": message_id,
                "role": "assistant",
                "parts": [
                    {
                        "type": f"tool-{call['toolName']}",
                        "toolCallId": call["toolCallId"],
                        "state": "approval-responded",
                        "input": call["input"],
                        "approval": {"id": request["approvalId"], "approved": True},
                    },
                ],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
        "mode": mode,
    }


async def test_a_new_thread_reads_auto(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    conversation_id = uuid4()
    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="Hello there.",
        conversation_id=conversation_id,
    )
    detail = await _detail(app, authed_user_id, conversation_id)
    assert detail["mode"] == "auto"


async def test_the_mode_a_message_carries_sticks(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    conversation_id = uuid4()
    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="Which stages express these genes?",
        conversation_id=conversation_id,
        mode="explore",
    )
    detail = await _detail(app, authed_user_id, conversation_id)
    assert detail["mode"] == "explore"


async def test_an_approval_resume_does_not_move_the_mode(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    conversation_id = uuid4()
    asked = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_REMEMBER_PROMPT,
        conversation_id=conversation_id,
        mode="build",
    )
    await turn_with_body(
        app,
        authed_user_id,
        in_memory_jobs,
        body=_approval_body(conversation_id, asked, mode="explore"),
    )
    detail = await _detail(app, authed_user_id, conversation_id)
    assert detail["mode"] == "build"


async def test_the_list_carries_no_mode(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="Hello there.",
        mode="explore",
    )
    async with client_for(app, authed_user_id) as client:
        rows = (await client.get("/api/v1/conversations")).json()
    assert [row["mode"] for row in rows] == [None]
