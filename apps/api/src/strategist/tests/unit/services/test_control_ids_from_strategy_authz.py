"""Importing controls from a strategy is scoped to the caller."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from strategist.platform.errors import ErrorCode, NotFoundError
from strategist.services.eval import StrategyGeneIdsResult
from strategist.services.experiment import control_sourcing

_CALLER = UUID(int=7)


@pytest.fixture
def session() -> AsyncSession:
    """An unbound session; the lookup under test is faked, so it is unused."""
    return AsyncSession()


@dataclass
class _FakeGeneIds:
    """Records the arguments the service layer forwards."""

    result: StrategyGeneIdsResult
    seen_user_ids: list[UUID] = field(default_factory=list)

    async def __call__(
        self,
        session: AsyncSession,
        strategy_id: UUID,
        site_id: str,
        user_id: UUID,
    ) -> StrategyGeneIdsResult:
        del session, strategy_id, site_id
        self.seen_user_ids.append(user_id)
        return self.result


async def _raise_not_found(
    session: AsyncSession,
    strategy_id: UUID,
    site_id: str,
    user_id: UUID,
) -> StrategyGeneIdsResult:
    del session, strategy_id, site_id, user_id
    raise NotFoundError(
        code=ErrorCode.STRATEGY_NOT_FOUND,
        title="conversation not found",
    )


async def test_the_callers_user_id_reaches_the_lookup(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
) -> None:
    fake = _FakeGeneIds(
        result=StrategyGeneIdsResult(gene_ids=["PF3D7_0100100"], estimated_size=1),
    )
    monkeypatch.setattr(control_sourcing, "get_strategy_gene_ids", fake)

    result = await control_sourcing.control_ids_from_strategy(
        session,
        uuid4(),
        "plasmodb",
        _CALLER,
    )

    assert fake.seen_user_ids == [_CALLER]
    assert result.gene_ids == ["PF3D7_0100100"]
    assert result.error is None


async def test_a_strategy_the_caller_does_not_own_reports_an_error(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
) -> None:
    monkeypatch.setattr(control_sourcing, "get_strategy_gene_ids", _raise_not_found)

    result = await control_sourcing.control_ids_from_strategy(
        session,
        uuid4(),
        "plasmodb",
        _CALLER,
    )

    assert result.gene_ids == []
    assert result.error == "Strategy not found"


async def test_a_strategy_without_results_forwards_the_error(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
) -> None:
    fake = _FakeGeneIds(
        result=StrategyGeneIdsResult(error="No WDK strategy linked"),
    )
    monkeypatch.setattr(control_sourcing, "get_strategy_gene_ids", fake)

    result = await control_sourcing.control_ids_from_strategy(
        session,
        uuid4(),
        "plasmodb",
        _CALLER,
    )

    assert result.gene_ids == []
    assert result.error == "No WDK strategy linked"
