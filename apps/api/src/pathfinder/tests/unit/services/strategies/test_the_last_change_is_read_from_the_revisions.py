"""The thread's last change is read from the revision it ends on and the one
before its last change."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.domain.last_change import LastChange
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.persistence.models import StrategyRevisionView
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.services.strategies.revision_ops import last_change

_TEXT = StrategyStepNode(id="step_text", search_name="GenesByText")
_JOINED = StrategyAst(
    record_type="transcript",
    root=StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=_TEXT,
        secondary_input=StrategyStepNode(
            id="step_sp",
            search_name="GenesWithSignalPeptide",
            display_name="Predicted Signal Peptide",
        ),
    ),
    step_counts={"step_text": 68, "step_sp": 431, "step_join": 17},
)
_TEXT_ALONE = StrategyAst(
    record_type="transcript", root=_TEXT, step_counts={"step_text": 68}
)


def _row(row_id: int, ast: StrategyAst) -> StrategyRevisionView:
    return StrategyRevisionView(
        id=row_id,
        conversation_id=uuid4(),
        revision=strategy_revision(ast),
        record_type="transcript",
        strategy_ast=ast.model_dump(by_alias=True, mode="json", exclude_none=True),
        message_id=uuid4(),
        created_at=datetime.now(UTC),
    )


def _rows(
    monkeypatch: pytest.MonkeyPatch,
    latest: StrategyRevisionView | None,
    previous: StrategyRevisionView | None,
) -> None:
    async def _latest(
        _repo: StrategyRevisionRepository, _conversation_id: UUID
    ) -> StrategyRevisionView | None:
        return latest

    async def _previous(
        _repo: StrategyRevisionRepository,
        _conversation_id: UUID,
        *,
        before_row_id: int,
        revision: str,
    ) -> StrategyRevisionView | None:
        assert latest is not None
        assert (before_row_id, revision) == (latest.id, latest.revision)
        return previous

    monkeypatch.setattr(StrategyRevisionRepository, "latest", _latest)
    monkeypatch.setattr(StrategyRevisionRepository, "newest_turn_end_unlike", _previous)


async def test_a_delete_reads_both_counts_from_the_two_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _rows(monkeypatch, _row(9, _TEXT_ALONE), _row(4, _JOINED))

    found = await last_change(AsyncSession(), conversation_id=uuid4())

    assert found == LastChange(
        before=17, after=68, what="deleted Predicted Signal Peptide"
    )


async def test_a_thread_s_first_strategy_is_its_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _rows(monkeypatch, _row(4, _JOINED), None)

    found = await last_change(AsyncSession(), conversation_id=uuid4())

    assert found == LastChange(before=None, after=17, what="built the strategy")


async def test_a_thread_with_no_strategy_has_no_last_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _rows(monkeypatch, None, None)

    assert [await last_change(AsyncSession(), conversation_id=uuid4())] == [None]
