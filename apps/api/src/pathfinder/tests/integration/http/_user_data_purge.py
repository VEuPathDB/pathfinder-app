"""The user, the client and the WDK doubles the purge route tests share."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails

from pathfinder.persistence.models import (
    STAGED,
    ConversationStrategy,
    EvalStagedCase,
    ExperimentRow,
    User,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.security import create_user_token
from pathfinder.services import user_data
from pathfinder.tests.integration.http.conftest import other_application_client_for

SITE = "plasmodb"
OTHER_SITE = "toxodb"
MINE = 101
THEIRS = 202
UNREFERENCED = 303


@dataclass(frozen=True)
class _Summary:
    strategy_id: int


@dataclass
class FakeStrategyApi:
    """Records the WDK strategies a purge asks it to delete."""

    deleted: list[int] = field(default_factory=list)

    async def list_strategies(self) -> list[_Summary]:
        return [_Summary(MINE), _Summary(THEIRS), _Summary(UNREFERENCED)]

    async def delete_strategy(self, strategy_id: int) -> None:
        self.deleted.append(strategy_id)


def reading_api() -> StrategyAPI:
    """Answers the website-open read with a one-step strategy."""
    api = Mock(spec=StrategyAPI)
    api.get_strategy = AsyncMock(
        return_value=WDKStrategyDetails.model_validate(
            {
                "strategyId": MINE,
                "rootStepId": 1,
                "name": "made on the website",
                "stepTree": {"stepId": 1},
                "steps": {
                    "1": {
                        "id": 1,
                        "searchName": "GenesByTaxon",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": 3,
                    }
                },
                "recordClassName": "transcript",
            }
        )
    )
    return api


@pytest.fixture
def wdk_api(monkeypatch: pytest.MonkeyPatch) -> FakeStrategyApi:
    api = FakeStrategyApi()
    monkeypatch.setattr(user_data, "get_strategy_api", lambda _site: api)
    return api


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


@pytest.fixture
async def api_client(
    app: FastAPI,
    patch_app_db_engine: None,
    app_memory_store: MemoryStore,
    seed_user: User,
) -> AsyncGenerator[httpx.AsyncClient]:
    del patch_app_db_engine, app_memory_store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        client.cookies.set("pathfinder-auth", create_user_token(seed_user.id))
        yield client


@pytest.fixture
async def other_application_client(
    app: FastAPI,
    patch_app_db_engine: None,
    app_memory_store: MemoryStore,
    seed_user: User,
    other_application: str,
) -> AsyncGenerator[httpx.AsyncClient]:
    """The same user, calling from a second application."""
    del patch_app_db_engine, app_memory_store, other_application
    async with other_application_client_for(app, seed_user.id) as client:
        yield client


async def add_conv(
    session: AsyncSession,
    user_id: UUID,
    *,
    site_id: str,
    wdk_strategy_id: int | None,
    created_here: bool,
    application_id: str = "pathfinder",
) -> UUID:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user_id,
        application_id=application_id,
        site_id=site_id,
        name="c",
    )
    session.add(conv)
    await session.flush()
    if wdk_strategy_id is not None:
        session.add(
            ConversationStrategy(
                conversation_id=conv.id,
                wdk_strategy_id=wdk_strategy_id,
                wdk_strategy_created_here=created_here,
            ),
        )
        await session.flush()
    await session.commit()
    return conv.id


async def add_experiment(
    session: AsyncSession,
    user_id: UUID,
    *,
    site_id: str,
    wdk_strategy_id: int,
) -> str:
    """One stored run whose persisted strategy PathFinder created on the site."""
    experiment_id = f"exp-{wdk_strategy_id}"
    session.add(
        ExperimentRow(
            id=experiment_id,
            site_id=site_id,
            user_id=user_id,
            application_id="pathfinder",
            name="a run",
            status="completed",
            data={"id": experiment_id, "wdkStrategyId": wdk_strategy_id},
        ),
    )
    await session.commit()
    return experiment_id


async def add_staged_case(
    session: AsyncSession,
    user_id: UUID,
    *,
    site_id: str,
    conversation_id: UUID,
    application_id: str = "pathfinder",
) -> UUID:
    """One eval candidate awaiting curation, named by its site."""
    staging_id = uuid4()
    session.add(
        EvalStagedCase(
            id=staging_id,
            user_id=user_id,
            source_conversation_id=conversation_id,
            application_id=application_id,
            site_id=site_id,
            assistant_id=PATHFINDER_ASSISTANT_ID,
            content_hash=staging_id.hex,
            extract={"siteId": site_id},
            status=STAGED,
        ),
    )
    await session.commit()
    return staging_id
