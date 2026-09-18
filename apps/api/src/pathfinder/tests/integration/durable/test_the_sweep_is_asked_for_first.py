"""The Lead's sweep asks the user first, and the yes defers the durable job.

The whole PathFinder assistant over the real chat route, the real turn graph
and the real registration. Only the model is a double: it plays the user's
outright request to tune a step, which the Lead's own rule answers with the
call. Whether the Lead offers a sweep in prose after a weak control test is
the model's judgment; the rule it reads is held by the instruction test.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for

SWEEP_TOOL = "optimize_search_parameters"
SWEEP_PROMPT = "tune the parameters of that step against my controls"
SWEEP_STEP_ID = 440230693
_DURABLE_JOB = f"durable:{SWEEP_TOOL}"
_TIMEOUT_SECONDS = 120.0


async def _turn(
    app: FastAPI,
    user_id: UUID,
    jobs: InMemoryConnector,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    queued = len(chat_turn_jobs(jobs))
    async with client_for(app, user_id) as client:
        post = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=_TIMEOUT_SECONDS),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(jobs, queued),
            timeout=_TIMEOUT_SECONDS,
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=_TIMEOUT_SECONDS)
    assert response.status_code == 200, response.text
    return parse_sse_body(response.text)


def _sweep_jobs(jobs: InMemoryConnector) -> list[dict[str, Any]]:
    return [job for job in jobs.jobs.values() if job["task_name"] == _DURABLE_JOB]


def _approval_call_id(chunks: list[dict[str, Any]]) -> str:
    asked = [c for c in chunks if c["type"] == "tool-approval-request"]
    return str(asked[0]["toolCallId"])


def _approval_body(
    conversation_id: UUID,
    call_id: str,
    *,
    approved: bool,
) -> dict[str, Any]:
    """The body the client sends when the user answers the sweep's card."""
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
                        "type": f"tool-{SWEEP_TOOL}",
                        "toolCallId": call_id,
                        "state": "approval-responded",
                        "input": {"wdkStepId": SWEEP_STEP_ID},
                        "approval": {"id": call_id, "approved": approved},
                    },
                ],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
    }


async def test_the_sweep_asks_before_it_runs(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb

    chunks = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        chat_post_body(uuid4(), SWEEP_PROMPT),
    )

    asked = [c for c in chunks if c["type"] == "tool-approval-request"]
    offered = [
        c
        for c in chunks
        if c["type"] == "tool-input-available" and c["toolName"] == SWEEP_TOOL
    ]

    assert [c["input"]["wdk_step_id"] for c in offered] == [SWEEP_STEP_ID]
    assert [c["toolCallId"] for c in asked] == [c["toolCallId"] for c in offered]
    assert _sweep_jobs(in_memory_jobs) == []


async def test_the_users_yes_defers_the_sweep(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conversation_id = uuid4()
    asked = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        chat_post_body(conversation_id, SWEEP_PROMPT),
    )

    chunks = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        _approval_body(conversation_id, _approval_call_id(asked), approved=True),
    )

    started = [c for c in chunks if c["type"] == "data-background-task-started"]
    assert [c["data"]["toolName"] for c in started] == [SWEEP_TOOL]
    assert len(_sweep_jobs(in_memory_jobs)) == 1


async def test_a_refused_sweep_defers_nothing(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conversation_id = uuid4()
    asked = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        chat_post_body(conversation_id, SWEEP_PROMPT),
    )
    call_id = _approval_call_id(asked)

    chunks = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        _approval_body(conversation_id, call_id, approved=False),
    )

    denials = [c for c in chunks if c["type"] == "tool-output-denied"]
    assert [c["toolCallId"] for c in denials] == [call_id]
    assert _sweep_jobs(in_memory_jobs) == []
