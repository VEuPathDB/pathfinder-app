"""The refresh route answers with the counts VEuPathDB holds right now.

It is the way out of a strategy whose stored numbers no longer describe it:
the thread's session is loaded, the site is read, what it answers replaces
every stored count, and the conversation is answered from the row that write
leaves behind.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from veupathdb.domain.strategy import StrategyAst
from veupathdb.wdk import WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import (
    AppError,
    ErrorCode,
    SiteUnavailableError,
)
from pathfinder.services.conversations import strategy_ops
from pathfinder.services.strategies import live_counts
from pathfinder.services.strategies.context import StrategyMutationContext

_SITE = "vectorbase"
_STRATEGY = 900
_LEAF = "step_text"
_ROOT = "step_root"
_WDK_IDS = {_LEAF: 11, _ROOT: 12}
_RECORDED = {_LEAF: 0, _ROOT: 5}
_LIVE = {_LEAF: 71, _ROOT: 159}


def _ast(*, pushed: bool) -> StrategyAst:
    """The stored tree, with the counts an earlier turn recorded."""
    return StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "root": {
                "id": _ROOT,
                "searchName": "__transform__",
                "operator": "INTERSECT",
                "primaryInput": {"id": _LEAF, "searchName": "GenesByText"},
                "secondaryInput": {"id": "step_go", "searchName": "GenesByGoTerm"},
            },
            "stepCounts": _RECORDED,
            **({"wdkStepIds": _WDK_IDS} if pushed else {}),
        }
    )


def _thread(
    ast: StrategyAst | None, *, pushed: bool = True
) -> tuple[Conversation, ConversationStrategyView]:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        assistant_id="pathfinder",
        site_id=_SITE,
        name="proteases",
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        wdk_strategy_id=_STRATEGY if pushed else None,
        wdk_strategy_created_here=pushed,
        is_saved=False,
        step_count=3 if ast is not None else 0,
        gene_set_auto_imported=False,
        imported_saved_strategy_ids=[],
        estimated_size=None,
        strategy_ast=(
            {}
            if ast is None
            else ast.model_dump(by_alias=True, exclude_none=True, mode="json")
        ),
    )
    return conversation, strategy


class _StubAPI:
    """A site that answers the live sizes for the strategy's steps."""

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": "proteases",
                "rootStepId": _WDK_IDS[_ROOT],
                "stepTree": {"stepId": _WDK_IDS[_ROOT]},
                "steps": {
                    str(_WDK_IDS[local_id]): {
                        "id": _WDK_IDS[local_id],
                        "searchName": "GenesByText",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": size,
                    }
                    for local_id, size in _LIVE.items()
                },
            }
        )


class _SiteIsDown:
    """A site that answers nothing at all."""

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del strategy_id, user_id
        raise _NOT_ANSWERING


_NOT_ANSWERING = OSError("the site is not answering")


class _Repo(ConversationRepository):
    """The thread the lock reads back, updated by whatever the refresh persists."""

    def __init__(self, thread: tuple[Conversation, ConversationStrategyView]) -> None:
        self.thread = thread

    async def get_with_strategy(
        self, conversation_id: UUID
    ) -> tuple[Conversation, ConversationStrategyView]:
        del conversation_id
        return self.thread


def _install(
    monkeypatch: pytest.MonkeyPatch,
    repo: _Repo,
    api: _StubAPI | _SiteIsDown,
) -> None:
    """Serve the stored thread, the lock, the persist and the site to the refresh."""

    async def _owned(*_args: Any, **_kwargs: Any) -> Any:
        return repo.thread

    @asynccontextmanager
    async def _lock(*_args: Any, **_kwargs: Any) -> AsyncIterator[None]:
        yield None

    async def _persist(
        *, deps: StrategyMutationContext, graph: StrategyGraph, sync_result: Any
    ) -> None:
        del sync_result
        written = graph.to_strategy_ast(sync_state=deps.strategy_session.sync_state)
        assert written is not None
        conversation, strategy = repo.thread
        repo.thread = (
            conversation,
            strategy.model_copy(
                update={
                    "strategy_ast": written.model_dump(
                        by_alias=True, exclude_none=True, mode="json"
                    )
                }
            ),
        )

    monkeypatch.setattr(strategy_ops, "get_owned_thread", _owned)
    monkeypatch.setattr(strategy_ops, "strategy_write_lock", _lock)
    monkeypatch.setattr(strategy_ops, "ConversationRepository", lambda _session: repo)
    monkeypatch.setattr(strategy_ops, "persist_strategy_ast_to_conversation", _persist)
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda _site_id: api)


@pytest.fixture
def refreshed(monkeypatch: pytest.MonkeyPatch) -> _Repo:
    """A pushed thread whose stored counts are out of date, and a site that answers."""
    repo = _Repo(_thread(_ast(pushed=True)))
    _install(monkeypatch, repo, _StubAPI())
    return repo


async def _run(repo: _Repo) -> dict[str, int | None]:
    response = await strategy_ops.refresh_counts(
        repo,
        repo.thread[0].id,
        repo.thread[0].user_id,
        site_id=_SITE,
    )
    return {step.id: step.estimated_size for step in response.steps}


def _stored_counts(repo: _Repo) -> dict[str, int]:
    return dict(
        StrategyAst.model_validate(repo.thread[1].strategy_ast).step_counts or {}
    )


@pytest.mark.asyncio
async def test_the_answer_carries_the_live_size_of_every_step(
    refreshed: _Repo,
) -> None:
    """The third step has no WDK id, so the site answers no size for it."""
    sizes = await _run(refreshed)

    assert sizes == {_LEAF: _LIVE[_LEAF], _ROOT: _LIVE[_ROOT], "step_go": None}


class TestARefreshTheSiteDidNotAnswerIsARefusal:
    """A refresh is the way out of stale numbers, so it never confirms them."""

    @pytest.fixture
    def unreadable(self, monkeypatch: pytest.MonkeyPatch) -> _Repo:
        repo = _Repo(_thread(_ast(pushed=True)))
        _install(monkeypatch, repo, _SiteIsDown())
        return repo

    @pytest.mark.asyncio
    async def test_the_refresh_reports_the_site(self, unreadable: _Repo) -> None:
        with pytest.raises(SiteUnavailableError) as refusal:
            await _run(unreadable)

        assert refusal.value.code == ErrorCode.SITE_UNAVAILABLE
        assert refusal.value.status == 503

    @pytest.mark.asyncio
    async def test_the_stored_counts_are_left_alone(self, unreadable: _Repo) -> None:
        with pytest.raises(SiteUnavailableError):
            await _run(unreadable)

        assert _stored_counts(unreadable) == _RECORDED


class TestAStrategyTheSiteDoesNotHoldHasNothingToRefresh:
    @pytest.mark.asyncio
    async def test_a_strategy_never_pushed_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No WDK strategy means no counts to read, and no site to blame."""
        repo = _Repo(_thread(_ast(pushed=False), pushed=False))
        _install(monkeypatch, repo, _StubAPI())

        with pytest.raises(AppError) as refusal:
            await _run(repo)

        assert (refusal.value.code, refusal.value.status) == (
            ErrorCode.INVALID_STRATEGY,
            409,
        )

    @pytest.mark.asyncio
    async def test_a_thread_with_no_steps_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _Repo(_thread(None))
        _install(monkeypatch, repo, _StubAPI())

        with pytest.raises(AppError) as refusal:
            await _run(repo)

        assert (refusal.value.code, refusal.value.status, refusal.value.detail) == (
            ErrorCode.INVALID_STRATEGY,
            409,
            "Add a step to the strategy before asking for its counts.",
        )
