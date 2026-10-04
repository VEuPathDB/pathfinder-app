"""A generated name records the steps it was written over; a chosen name records none."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb.wdk import build_wdk_step_tree

from pathfinder.domain.strategy.operations import UpdateStrategyMetaOp
from pathfinder.services.strategies import naming
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.naming import (
    name_if_unnamed,
    rename_strategy_everywhere,
)
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)
from pathfinder.tests.unit.services.strategies._thread_names import (
    Sets,
    Threads,
    thread_row,
)

_TITLE = "Exported Kinases in Gametocytes"


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    stub = StubAPI()
    monkeypatch.setattr(naming, "get_strategy_api", lambda _site: stub)
    return stub


@pytest.fixture
def sets(monkeypatch: pytest.MonkeyPatch) -> Sets:
    held = Sets()
    monkeypatch.setattr(naming, "GeneSetService", lambda _store: held)
    monkeypatch.setattr(naming, "get_gene_set_store", lambda: None)
    return held


def _serve(monkeypatch: pytest.MonkeyPatch, threads: Threads) -> None:
    @asynccontextmanager
    async def _locked(*_args: Any) -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(naming, "strategy_write_lock", _locked)
    monkeypatch.setattr(naming, "ConversationRepository", lambda _session: threads)


async def test_the_first_title_records_the_steps_it_names(
    api: StubAPI, sets: Sets
) -> None:
    threads = thread_row()

    await name_if_unnamed(threads, threads.conversation.id, title=_TITLE)

    assert threads.strategy.generated_name_steps == ["step_a"]


async def test_putting_the_name_back_keeps_the_record(api: StubAPI, sets: Sets) -> None:
    threads = thread_row(
        name="Kinase Hunt", ast_name="New Conversation", generated_name_steps=[]
    )

    await name_if_unnamed(threads, threads.conversation.id, title=_TITLE)

    assert (threads.ast_name, threads.strategy.generated_name_steps) == (
        "Kinase Hunt",
        [],
    )


async def test_a_rename_by_a_person_clears_the_record(
    monkeypatch: pytest.MonkeyPatch, api: StubAPI, sets: Sets
) -> None:
    threads = thread_row(name="Kinase Hunt", generated_name_steps=["step_a"])
    _serve(monkeypatch, threads)

    await rename_strategy_everywhere(
        threads.conversation.id, _TITLE, session_factory=async_session_factory
    )

    assert (threads.conversation.name, threads.strategy.generated_name_steps) == (
        _TITLE,
        None,
    )


async def test_a_graph_rename_clears_the_record(
    monkeypatch: pytest.MonkeyPatch, sets: Sets
) -> None:
    install_stub_api(monkeypatch)
    threads = thread_row(
        name="Kinase Hunt", ast_name="Kinase Hunt", generated_name_steps=["step_a"]
    )

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
    state.wdk_strategy_name = "Kinase Hunt"

    await apply_and_commit(
        deps=StrategyMutationContext(
            site_id="plasmodb",
            strategy_session=session,
            conversation_id=threads.conversation.id,
        ),
        op=UpdateStrategyMetaOp(name=_TITLE),
    )

    assert (threads.conversation.name, threads.strategy.generated_name_steps) == (
        _TITLE,
        None,
    )
