"""A declared source the deployment does not admit still lets the turn finish."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.platform.security import create_user_token
from pathfinder.platform.tool_sources import admitted_tool_sources
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)

_OK = 200


async def test_an_unadmitted_source_leaves_the_turn_whole(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
    monkeypatch: Any,
) -> None:
    """The assistant asks for the research server; this run admits none."""
    del patch_app_db_engine, signed_in_to_veupathdb, monkeypatch
    declared = build_pathfinder_spec().tool_sources
    assert [source.name for source in declared] == ["research"]
    assert admitted_tool_sources().resolve(declared[0].source_id) is None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": create_user_token(authed_user_id)},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=chat_post_body(uuid4(), "hi"),
                timeout=60.0,
            ),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(in_memory_jobs),
            timeout=30.0,
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=60.0)

    assert response.status_code == _OK, response.text
    chunks = parse_sse_body(response.text)
    types = [chunk["type"] for chunk in chunks]
    assert "error" not in types
    assert types[-2:] == ["finish", "done"]
