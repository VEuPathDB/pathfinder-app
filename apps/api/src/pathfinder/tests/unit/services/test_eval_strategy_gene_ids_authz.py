"""``get_strategy_gene_ids`` serves only the caller's own conversation."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from assistant_core.errors import ConversationNotFoundError
from assistant_core.platform.context import application_id_ctx
from sqlalchemy.ext.asyncio import AsyncSession

import pathfinder.services.eval
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID

_OWNER = UUID(int=1)
_INTRUDER = UUID(int=2)


@pytest.fixture(autouse=True)
def calling_application() -> Iterator[None]:
    """A served request names this application, the way security does."""
    reset = application_id_ctx.set(PATHFINDER_APPLICATION_ID)
    try:
        yield
    finally:
        application_id_ctx.reset(reset)


@pytest.fixture
def session() -> AsyncSession:
    """An unbound session; the repository under test is faked, so it is unused."""
    return AsyncSession()


@dataclass
class _Conversation:
    user_id: UUID
    id: UUID = field(default_factory=uuid4)
    application_id: str = PATHFINDER_APPLICATION_ID


@dataclass
class _Repo:
    """Stands in for the conversation repository."""

    conversation: _Conversation | None
    strategy: ConversationStrategyView = field(
        default_factory=ConversationStrategyView,
    )

    def __call__(self, session: AsyncSession) -> _Repo:
        del session
        return self

    async def get_by_id(self, conversation_id: UUID) -> _Conversation | None:
        del conversation_id
        return self.conversation

    async def get_strategy(self, conversation_id: UUID) -> ConversationStrategyView:
        del conversation_id
        return self.strategy


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    conversation: _Conversation | None,
    strategy: ConversationStrategyView | None = None,
) -> None:
    repo = _Repo(conversation, strategy or ConversationStrategyView())
    monkeypatch.setattr(pathfinder.services.eval, "ConversationRepository", repo)


async def test_another_users_conversation_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
) -> None:
    _wire(
        monkeypatch,
        _Conversation(user_id=_OWNER),
        ConversationStrategyView(wdk_strategy_id=4242),
    )

    with pytest.raises(ConversationNotFoundError):
        await pathfinder.services.eval.get_strategy_gene_ids(
            session,
            uuid4(),
            "plasmodb",
            _INTRUDER,
        )


async def test_missing_conversation_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
) -> None:
    _wire(monkeypatch, None)

    with pytest.raises(ConversationNotFoundError):
        await pathfinder.services.eval.get_strategy_gene_ids(
            session,
            uuid4(),
            "plasmodb",
            _OWNER,
        )


async def test_owner_without_a_wdk_link_keeps_the_wire_shape(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
) -> None:
    _wire(monkeypatch, _Conversation(user_id=_OWNER))

    result = await pathfinder.services.eval.get_strategy_gene_ids(
        session,
        uuid4(),
        "plasmodb",
        _OWNER,
    )

    assert result.gene_ids == []
    assert result.error == "No WDK strategy linked"
    assert result.estimated_size is None
    assert result.model_dump(by_alias=True, exclude_none=True) == {
        "geneIds": [],
        "error": "No WDK strategy linked",
    }


def test_a_populated_result_serializes_to_the_documented_wire_shape() -> None:
    result = pathfinder.services.eval.StrategyGeneIdsResult(
        gene_ids=["PF3D7_0100100", "PF3D7_0100200"],
        estimated_size=2,
    )

    assert result.model_dump(by_alias=True, exclude_none=True) == {
        "geneIds": ["PF3D7_0100100", "PF3D7_0100200"],
        "estimatedSize": 2,
    }
