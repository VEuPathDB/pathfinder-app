"""The thread's name reaches its stored strategy, its WDK strategy and its set.

The conversation holds the name; every other place carries a copy of it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.errors import WDKError
from veupathdb.wdk import build_wdk_step_tree

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import TurnMarkers
from pathfinder.ai.tools.standalone.conversation import rename_strategy
from pathfinder.domain.strategy.operations import UpdateStrategyMetaOp
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies import naming
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.naming import (
    NamedThread,
    TitleWrite,
    name_if_unnamed,
    rename_strategy_everywhere,
)
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_WDK_ID = 330679883
_TITLE = "Exported kinases in gametocytes"


def _ast(name: str | None) -> dict[str, Any]:
    return StrategyAst(
        record_type="transcript",
        name=name,
        root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
    ).model_dump(by_alias=True, exclude_none=True, mode="json")


@dataclass
class _Threads:
    """One thread and its strategy row, written the way the repository writes."""

    conversation: Conversation
    strategy: ConversationStrategyView
    suffix: str = ""
    """What the store appends to keep a name unique."""

    async def get_with_strategy(
        self, conversation_id: UUID, /
    ) -> ConversationWithStrategy | None:
        if conversation_id != self.conversation.id:
            return None
        return self.conversation, self.strategy

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate, /
    ) -> None:
        del conversation_id
        if upd.name is not None:
            upd.name = f"{upd.name}{self.suffix}"
            self.conversation.name = upd.name
        if upd.strategy_ast is not None:
            self.strategy = self.strategy.model_copy(
                update={
                    "strategy_ast": upd.strategy_ast.model_dump(
                        by_alias=True, exclude_none=True, mode="json"
                    )
                }
            )

    @property
    def ast_name(self) -> str | None:
        return StrategyAst.model_validate(self.strategy.strategy_ast).name


def _threads(
    *,
    name: str = "",
    ast_name: str | None = "New Conversation",
    gene_set_id: str | None = None,
) -> _Threads:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        name=name,
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        wdk_strategy_id=_WDK_ID,
        strategy_ast=_ast(ast_name),
        gene_set_id=gene_set_id,
        gene_set_auto_imported=gene_set_id is not None,
    )
    return _Threads(conversation=conversation, strategy=strategy)


@dataclass
class _Sets:
    held: dict[str, GeneSet] = field(default_factory=dict)

    async def get_for_user(self, user_id: UUID, gene_set_id: str) -> GeneSet:
        del user_id
        found = self.held.get(gene_set_id)
        if found is None:
            raise NotFoundError(detail=gene_set_id)
        return found

    async def rename(self, gene_set: GeneSet, name: str) -> None:
        gene_set.name = name


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    stub = StubAPI()
    monkeypatch.setattr(naming, "get_strategy_api", lambda _site: stub)
    return stub


@pytest.fixture
def sets(monkeypatch: pytest.MonkeyPatch) -> _Sets:
    held = _Sets()
    monkeypatch.setattr(naming, "GeneSetService", lambda _store: held)
    monkeypatch.setattr(naming, "get_gene_set_store", lambda: None)
    return held


def _set(name: str, owner: UUID) -> GeneSet:
    return GeneSet(
        id="gs-1",
        name=name,
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100"],
        source="strategy",
        user_id=owner,
    )


@dataclass
class _Lock:
    """The thread's strategy lock, recording whether it is held."""

    held: bool = False
    held_at_wdk: list[bool] = field(default_factory=list)


def _install(monkeypatch: pytest.MonkeyPatch, api: StubAPI, threads: _Threads) -> _Lock:
    """Serve ``threads`` under a recorded lock, and record the lock at WDK."""
    lock = _Lock()

    @asynccontextmanager
    async def _locked(*_args: Any) -> AsyncIterator[None]:
        lock.held = True
        try:
            yield None
        finally:
            lock.held = False

    recorded = api.update_strategy

    async def _update(strategy_id: int, name: str | None = None) -> object:
        lock.held_at_wdk.append(lock.held)
        return await recorded(strategy_id, name=name)

    monkeypatch.setattr(naming, "strategy_write_lock", _locked)
    monkeypatch.setattr(naming, "ConversationRepository", lambda _session: threads)
    monkeypatch.setattr(api, "update_strategy", _update)
    return lock


async def _rename(threads: _Threads, name: str = _TITLE) -> str | None:
    return await rename_strategy_everywhere(
        threads.conversation.id, name, session_factory=async_session_factory
    )


class TestARename:
    async def test_it_writes_the_thread_the_stored_strategy_and_wdk(
        self, api: StubAPI, sets: _Sets, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        threads = _threads()
        lock = _install(monkeypatch, api, threads)

        stored = await _rename(threads)

        assert (stored, threads.conversation.name, threads.ast_name) == (
            _TITLE,
            _TITLE,
            _TITLE,
        )
        assert [(c.kwargs["strategy_id"], c.kwargs["name"]) for c in api.calls] == [
            (_WDK_ID, _TITLE)
        ]
        assert lock.held_at_wdk == [False]

    async def test_every_copy_takes_the_name_the_store_kept(
        self, api: StubAPI, sets: _Sets, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        threads = _threads()
        threads.suffix = " (1)"
        _install(monkeypatch, api, threads)

        await _rename(threads)

        assert threads.ast_name == f"{_TITLE} (1)"
        assert api.calls[0].kwargs["name"] == f"{_TITLE} (1)"

    @pytest.mark.parametrize(
        "failure",
        [WDKError("401 Unauthorized", status=401), RuntimeError("store closed")],
    )
    async def test_wdk_failing_the_name_leaves_the_thread_renamed(
        self,
        api: StubAPI,
        sets: _Sets,
        monkeypatch: pytest.MonkeyPatch,
        failure: Exception,
    ) -> None:
        async def _refuse(*_args: Any, **_kwargs: Any) -> None:
            raise failure

        monkeypatch.setattr(api, "update_strategy", _refuse)
        threads = _threads()
        monkeypatch.setattr(naming, "ConversationRepository", lambda _s: threads)
        _install_lock_only(monkeypatch)

        stored = await _rename(threads)

        assert (stored, threads.conversation.name, threads.ast_name) == (
            _TITLE,
            _TITLE,
            _TITLE,
        )

    async def test_a_wdk_that_hangs_is_left_after_the_bound(
        self, api: StubAPI, sets: _Sets, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _hang(*_args: Any, **_kwargs: Any) -> None:
            await asyncio.Event().wait()

        monkeypatch.setattr(api, "update_strategy", _hang)
        monkeypatch.setattr(naming, "WDK_RENAME_SECONDS", 0.05)
        threads = _threads()
        monkeypatch.setattr(naming, "ConversationRepository", lambda _s: threads)
        _install_lock_only(monkeypatch)

        stored = await asyncio.wait_for(_rename(threads), timeout=2)

        assert (stored, threads.ast_name) == (_TITLE, _TITLE)

    @pytest.mark.parametrize(
        ("previous", "set_name", "renamed"),
        [
            ("", "Kinases expressed in gametocytes", True),
            ("Kinase hunt", "Kinase hunt", True),
            ("Kinase hunt", f"WDK Strategy {_WDK_ID}", True),
            ("Kinase hunt", "My curated kinases", False),
        ],
    )
    async def test_the_imported_set_follows_only_a_name_it_was_given(
        self,
        api: StubAPI,
        sets: _Sets,
        monkeypatch: pytest.MonkeyPatch,
        previous: str,
        set_name: str,
        renamed: bool,
    ) -> None:
        threads = _threads(name=previous, gene_set_id="gs-1")
        sets.held["gs-1"] = _set(set_name, threads.conversation.user_id)
        _install(monkeypatch, api, threads)

        await _rename(threads)

        assert sets.held["gs-1"].name == (_TITLE if renamed else set_name)


def _install_lock_only(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _locked(*_args: Any) -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(naming, "strategy_write_lock", _locked)


class TestTheFirstTitle:
    """The title is written on the thread and its local copies; WDK comes after."""

    async def test_an_unnamed_thread_takes_the_title(
        self, api: StubAPI, sets: _Sets
    ) -> None:
        threads = _threads()

        title_write = await name_if_unnamed(
            threads, threads.conversation.id, title=_TITLE
        )

        assert title_write == TitleWrite(
            written=True,
            named=NamedThread(name=_TITLE, site_id="plasmodb", wdk_strategy_id=_WDK_ID),
        )
        assert (threads.conversation.name, threads.ast_name, api.calls) == (
            _TITLE,
            _TITLE,
            [],
        )

    async def test_a_named_thread_puts_its_name_back_on_a_stale_strategy(
        self, api: StubAPI, sets: _Sets
    ) -> None:
        threads = _threads(name="Kinase hunt", ast_name="New Conversation")

        title_write = await name_if_unnamed(
            threads, threads.conversation.id, title=_TITLE
        )

        assert title_write == TitleWrite(
            written=False,
            named=NamedThread(
                name="Kinase hunt", site_id="plasmodb", wdk_strategy_id=_WDK_ID
            ),
        )
        assert threads.ast_name == "Kinase hunt"

    async def test_a_named_thread_whose_strategy_agrees_writes_nothing(
        self, api: StubAPI, sets: _Sets
    ) -> None:
        threads = _threads(name="Kinase hunt", ast_name="Kinase hunt")

        title_write = await name_if_unnamed(
            threads, threads.conversation.id, title=_TITLE
        )

        assert title_write == TitleWrite(written=False)


async def test_a_graph_rename_renames_the_thread_and_the_push_names_wdk(
    monkeypatch: pytest.MonkeyPatch, sets: _Sets
) -> None:
    api = install_stub_api(monkeypatch)
    threads = _threads(name="Kinase hunt", ast_name="Kinase hunt")

    @asynccontextmanager
    async def _scope(_deps: StrategyMutationContext) -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(naming, "strategy_write_scope", _scope)
    monkeypatch.setattr(naming, "ConversationRepository", lambda _session: threads)
    root = combine("step_join", leaf("step_a"), leaf("step_b"))
    ids = {"step_a": 440537303, "step_b": 440537313, "step_join": 440537323}
    session = session_with(root, ids)
    state = ensure_sync_state(session)
    state.wdk_step_tree = build_wdk_step_tree(root, ids)
    state.wdk_strategy_name = "Kinase hunt"

    await apply_and_commit(
        deps=StrategyMutationContext(
            site_id="plasmodb",
            strategy_session=session,
            conversation_id=threads.conversation.id,
        ),
        op=UpdateStrategyMetaOp(name=_TITLE),
    )

    assert (threads.conversation.name, threads.ast_name) == (_TITLE, _TITLE)
    assert [c.kwargs["name"] for c in api.named("update_strategy")] == [_TITLE]


async def test_the_agents_rename_renames_the_thread_everywhere(
    monkeypatch: pytest.MonkeyPatch, api: StubAPI, sets: _Sets
) -> None:
    threads = _threads(name="Kinase hunt", ast_name="Kinase hunt")
    lock = _install(monkeypatch, api, threads)
    session = session_with(leaf("step_a"), {"step_a": 440537303})
    deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=threads.conversation.id,
        db_session_factory=async_session_factory,
        agent_state=AgentToolState(),
        turn_markers=TurnMarkers(),
    )

    await rename_strategy(run_context_for(deps), new_name=_TITLE, description="d")

    assert session.graph is not None
    assert (session.graph.name, threads.conversation.name, threads.ast_name) == (
        _TITLE,
        _TITLE,
        _TITLE,
    )
    assert [c.kwargs["name"] for c in api.named("update_strategy")] == [_TITLE]
    assert lock.held_at_wdk == [False]
