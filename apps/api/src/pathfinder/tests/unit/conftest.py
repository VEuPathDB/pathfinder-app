"""Shared fixtures for unit tests."""

from collections.abc import AsyncGenerator, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.config import get_settings
from pathfinder.tests._support.network_guard import refuse_every_connection

# Input screening.


@pytest.fixture
def input_screening_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Turns input screening on for one test."""
    monkeypatch.setenv("INPUT_SCREENING_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def input_screening_disabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Turns input screening off for one test."""
    monkeypatch.setenv("INPUT_SCREENING_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# Network guard.


@pytest.fixture(autouse=True)
def _no_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuses network connections for the duration of a unit test.

    A test that needs a real connection carries the `allow_network` marker.
    """
    if request.node.get_closest_marker("allow_network") is None:
        refuse_every_connection(monkeypatch, request.node.nodeid)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    async with session_maker() as session:
        yield session


@pytest.fixture
async def conv_repo(
    db_session: AsyncSession,
) -> ConversationRepository:
    return ConversationRepository(db_session)


@pytest.fixture
async def user_id(db_session: AsyncSession) -> UUID:
    """Create a User row and return its id."""
    uid = uuid4()
    db_session.add(User(id=uid))
    await db_session.flush()
    return uid


def populate_graph(graph: StrategyGraph, *steps: StrategyStepNode) -> None:
    """Add steps to graph bypassing single-root invariant for test setup."""
    for step in steps:
        graph.steps.update(flatten_tree(step))
    graph.recompute_roots()
