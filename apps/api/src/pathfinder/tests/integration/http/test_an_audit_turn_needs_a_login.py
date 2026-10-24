from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.identity import AUDIT_ASSISTANT_ID
from pathfinder.tests.integration.chat._helpers import chat_post_body
from pathfinder.tests.integration.http.conftest import bearer_client_for, make_user

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_UNAUTHORIZED = 401


async def test_an_audit_turn_without_a_registered_login_is_refused(
    app: FastAPI, db_session: AsyncSession
) -> None:
    owner = await make_user(db_session)
    body = chat_post_body(uuid4(), "Audit the gene models of Examplea alpha A")
    body["assistantId"] = AUDIT_ASSISTANT_ID

    async with bearer_client_for(app, owner.id) as client:
        response = await asyncio.wait_for(
            client.post("/api/v1/chat", json=body), timeout=10.0
        )

    assert (response.status_code, response.json()["code"]) == (
        _UNAUTHORIZED,
        "WDK_LOGIN_REQUIRED",
    )
