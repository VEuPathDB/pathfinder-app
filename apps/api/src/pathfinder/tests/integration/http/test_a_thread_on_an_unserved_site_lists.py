"""A thread on a site the deployment does not serve lists without its WDK link."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.wdk import reset_site_router

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.http.conftest import client_for, make_user

_E2E_SITES = Path(__file__).resolve().parents[7] / "e2e-sites.yaml"


@pytest.fixture
def six_sites(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The deployment serves the portal and five component sites, not giardiadb."""
    monkeypatch.setenv("VEUPATHDB_SITES_CONFIG", str(_E2E_SITES))
    get_settings.cache_clear()
    reset_site_router()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    reset_site_router()


async def _linked_thread(
    session: AsyncSession, user_id: UUID, site_id: str, wdk_id: int
) -> UUID:
    conversation_id = uuid4()
    session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conversation_id,
            user_id=user_id,
            site_id=site_id,
            name=f"{site_id} kinases",
        )
    )
    await session.flush()
    session.add(
        ConversationStrategy(conversation_id=conversation_id, wdk_strategy_id=wdk_id)
    )
    await session.commit()
    return conversation_id


async def test_the_unscoped_list_answers_every_row(
    app: FastAPI,
    patch_app_db_engine: None,
    six_sites: None,
    db_session: AsyncSession,
) -> None:
    del patch_app_db_engine, six_sites
    user = await make_user(db_session)
    served = await _linked_thread(db_session, user.id, "plasmodb", 123)
    unserved = await _linked_thread(db_session, user.id, "giardiadb", 124)

    async with client_for(app, user.id) as client:
        listed = await client.get("/api/v1/conversations")

    assert listed.status_code == 200, listed.text
    links = {row["id"]: row["wdkUrl"] for row in listed.json()}
    assert links == {
        str(served): "https://plasmodb.org/plasmo/app/workspace/strategies/123",
        str(unserved): None,
    }
