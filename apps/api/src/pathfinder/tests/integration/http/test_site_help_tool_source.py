"""Site help answers with tools a declared MCP source serves over the network.

The turn takes the whole path: the chat route defers the job, the worker
resolves the assistant's declaration against what this deployment admits,
opens a session to the served endpoint, and streams the calls back. A tool the
server marks read-only runs silently; the one that writes parks on an approval
card and runs when the user answers it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.mcp.admission import AdmittedSources, install_admitted_sources
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb_mcp.server import TOOLS

from pathfinder.assistants.site_help.mock import (
    CONTROL_TESTS_PROMPT,
    CONTROL_TESTS_REPLY,
    RECORD_TYPES_PROMPT,
    RECORD_TYPES_REPLY,
    WDK_CONTROL_TESTS_CALL_ID,
    WDK_CONTROL_TESTS_TOOL,
    WDK_RECORD_TYPES_TOOL,
)
from pathfinder.tests.integration.chat._helpers import chat_post_body
from pathfinder.tests.integration.http._wdk_mcp_double import (
    ANNOTATIONS,
    CONTROL_TEST_RESULT,
    RECORD_TYPES,
    SITE_HELP,
    admit_wdk_mcp,
    run_site_help_turn,
    served_double,
)
from pathfinder.tests.integration.http.conftest import make_user


@pytest.fixture(scope="module")
async def served_endpoint() -> AsyncIterator[str]:
    """One served double for the module. Every turn opens its own session."""
    async with served_double() as endpoint:
        yield endpoint


@pytest.fixture
def admitted_double(
    served_endpoint: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Admit the served double under the id site help declares."""
    with admit_wdk_mcp(served_endpoint, monkeypatch) as endpoint:
        yield endpoint


@pytest.fixture
def no_admitted_source() -> Iterator[None]:
    """A deployment that admits nothing, which is what a bare install is."""
    install_admitted_sources(AdmittedSources())
    yield
    install_admitted_sources(AdmittedSources())


async def _turn(
    app: FastAPI,
    user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    *,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    return await run_site_help_turn(app, user_id, in_memory_jobs, body)


def _prompt_body(conversation_id: UUID, prompt: str) -> dict[str, Any]:
    body = chat_post_body(conversation_id, prompt)
    body["assistantId"] = SITE_HELP
    return body


def _approval_body(conversation_id: UUID) -> dict[str, Any]:
    """The body the client sends when the user approves the parked call."""
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
                        "type": f"tool-{WDK_CONTROL_TESTS_TOOL}",
                        "toolCallId": WDK_CONTROL_TESTS_CALL_ID,
                        "state": "approval-responded",
                        "input": {},
                        "approval": {
                            "id": WDK_CONTROL_TESTS_CALL_ID,
                            "approved": True,
                        },
                    },
                ],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
        "assistantId": SITE_HELP,
    }


# The kinds PROTOCOL section 6.2 names for one call's arc, in no order.
_ARC_KINDS = frozenset(
    {
        "tool-input-start",
        "tool-input-available",
        "tool-approval-request",
        "tool-output-available",
        "tool-output-denied",
    },
)


def _of_type(chunks: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == kind]


def _arc(chunks: list[dict[str, Any]], tool_call_id: str) -> list[str]:
    """One call's chunk kinds, in the order the turn wrote them."""
    return [
        chunk["type"]
        for chunk in chunks
        if chunk.get("toolCallId") == tool_call_id and chunk["type"] in _ARC_KINDS
    ]


def _text(chunks: list[dict[str, Any]]) -> str:
    return "".join(c.get("delta", "") for c in chunks if c["type"] == "text-delta")


def test_the_double_answers_under_the_served_server_s_names_and_annotations() -> None:
    """A stand-in that drifts from the server proves nothing about it."""
    served = {row.fn.__name__: row.annotations for row in TOOLS}

    assert {name: served[name] for name in ANNOTATIONS} == ANNOTATIONS


async def test_a_read_only_tool_of_the_source_answers_inside_the_reply(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    admitted_double: str,
) -> None:
    del patch_app_db_engine, admitted_double
    owner = await make_user(db_session)

    chunks = await _turn(
        app,
        owner.id,
        in_memory_jobs,
        body=_prompt_body(uuid4(), RECORD_TYPES_PROMPT),
    )

    inputs = _of_type(chunks, "tool-input-available")
    outputs = _of_type(chunks, "tool-output-available")
    assert [c["toolName"] for c in inputs] == [WDK_RECORD_TYPES_TOOL]
    assert outputs[0]["output"] == RECORD_TYPES
    assert _of_type(chunks, "tool-approval-request") == []
    assert _of_type(chunks, "error") == []
    assert _text(chunks) == RECORD_TYPES_REPLY


async def test_the_writing_tool_of_the_source_asks_before_it_runs(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    admitted_double: str,
) -> None:
    del patch_app_db_engine, admitted_double
    owner = await make_user(db_session)

    chunks = await _turn(
        app,
        owner.id,
        in_memory_jobs,
        body=_prompt_body(uuid4(), CONTROL_TESTS_PROMPT),
    )

    assert _arc(chunks, WDK_CONTROL_TESTS_CALL_ID) == [
        "tool-input-start",
        "tool-input-available",
        "tool-approval-request",
    ]
    assert _of_type(chunks, "tool-output-available") == []
    assert [c["type"] for c in chunks][-2:] == ["finish", "done"]


async def test_the_answered_card_runs_the_source_s_tool_on_the_next_request(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    admitted_double: str,
) -> None:
    del patch_app_db_engine, admitted_double
    owner = await make_user(db_session)
    conversation_id = uuid4()
    await _turn(
        app,
        owner.id,
        in_memory_jobs,
        body=_prompt_body(conversation_id, CONTROL_TESTS_PROMPT),
    )

    chunks = await _turn(
        app,
        owner.id,
        in_memory_jobs,
        body=_approval_body(conversation_id),
    )

    # The resume re-enters the same call and answers it. The missing
    # tool-input-start is the runtime's open deviation from PROTOCOL 6.2,
    # filed as backlog/resumed-approval-turn-omits-tool-input-start.md.
    assert _arc(chunks, WDK_CONTROL_TESTS_CALL_ID) == [
        "tool-input-available",
        "tool-output-available",
    ]
    assert _of_type(chunks, "tool-output-available")[0]["output"] == CONTROL_TEST_RESULT
    assert _text(chunks) == CONTROL_TESTS_REPLY


async def test_a_deployment_that_admits_nothing_still_answers(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    no_admitted_source: None,
) -> None:
    """The declaration is optional, so an unadmitted source costs no turn."""
    del patch_app_db_engine, no_admitted_source
    owner = await make_user(db_session)

    chunks = await _turn(
        app,
        owner.id,
        in_memory_jobs,
        body=_prompt_body(uuid4(), "site help check"),
    )

    assert _of_type(chunks, "error") == []
    assert _text(chunks) == "Site help is online."
