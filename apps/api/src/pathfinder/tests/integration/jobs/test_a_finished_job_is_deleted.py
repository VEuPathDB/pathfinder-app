from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.tests.integration.chat._helpers import chat_turn_jobs, run_one_chat_turn


@pytest.fixture
async def chat_stack(
    patch_app_db_engine: None,
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb


async def test_a_chat_turn_leaves_no_job_row_once_it_finishes(
    app: FastAPI,
    chat_stack: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del chat_stack
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="hi",
    )

    assert [chunks[-2]["type"], chunks[-1]["type"]] == ["finish", "done"]
    assert chat_turn_jobs(in_memory_jobs) == []
