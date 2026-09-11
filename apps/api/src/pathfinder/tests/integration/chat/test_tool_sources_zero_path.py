"""A declared source the deployment does not admit still lets the turn finish."""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.platform.tool_sources import admitted_tool_sources
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn


async def test_an_unadmitted_source_leaves_the_turn_whole(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """The assistant asks for the research server; this run admits none."""
    del patch_app_db_engine, signed_in_to_veupathdb
    declared = build_pathfinder_spec().tool_sources
    assert [source.name for source in declared] == ["research"]
    assert admitted_tool_sources().resolve(declared[0].source_id) is None

    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="hi",
    )

    types = [chunk["type"] for chunk in chunks]
    assert "error" not in types
    assert types[-2:] == ["finish", "done"]
