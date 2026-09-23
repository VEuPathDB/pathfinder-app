"""A strategy pushed before its thread has a title carries the request's name.

The title then replaces that name on the thread, the AST, WDK and the imported set.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from assistant_core.persistence.repositories.conversation import (
    DEFAULT_CONVERSATION_NAME,
)

from pathfinder.domain.strategy.operations import ReplaceStrategyOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.services.strategies import commit, naming, persist, sync
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.naming import name_if_unnamed
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
    leaf,
)
from pathfinder.tests.unit.services.strategies._thread_names import (
    Sets,
    Threads,
    gene_set,
    thread_row,
)

_TITLE = "Exported kinases in gametocytes"


@pytest.fixture
def sets(monkeypatch: pytest.MonkeyPatch) -> Sets:
    held = Sets()
    monkeypatch.setattr(naming, "GeneSetService", lambda _store: held)
    monkeypatch.setattr(naming, "get_gene_set_store", lambda: None)
    return held


_REQUEST = "Find genes upregulated\n 24 hours post blood meal in Anopheles gambiae"
_PROVISIONAL = "Find genes upregulated 24 hours post blood meal in Anopheles..."


async def _no_catalog(*_args: Any) -> None:
    return None


def _write_through(monkeypatch: pytest.MonkeyPatch, threads: Threads) -> StubAPI:
    """Push through the real sync and persist every write on ``threads``."""
    api = install_stub_api(monkeypatch)

    @asynccontextmanager
    async def _scope(_deps: StrategyMutationContext) -> AsyncIterator[None]:
        yield None

    for module in (naming, persist):
        monkeypatch.setattr(module, "strategy_write_scope", _scope)
        monkeypatch.setattr(module, "ConversationRepository", lambda _s: threads)
    monkeypatch.setattr(naming, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(commit, "sync_strategy_for_site", sync.sync_strategy_for_site)
    monkeypatch.setattr(sync, "make_record_type_resolver", _no_catalog)
    monkeypatch.setattr(sync, "assign_step_record_classes", _no_catalog)
    monkeypatch.setattr(
        commit,
        "persist_strategy_ast_to_conversation",
        persist.persist_strategy_ast_to_conversation,
    )
    return api


async def test_the_first_push_carries_the_request_until_the_title_lands(
    monkeypatch: pytest.MonkeyPatch, sets: Sets
) -> None:
    threads = thread_row(gene_set_id="gs-1")
    threads.strategy = ConversationStrategyView(
        gene_set_id="gs-1", gene_set_auto_imported=True
    )
    sets.held["gs-1"] = gene_set(_PROVISIONAL, threads.conversation.user_id)
    api = _write_through(monkeypatch, threads)
    session = StrategySession(site_id="plasmodb")
    session.graph = StrategyGraph(
        graph_id=str(threads.conversation.id),
        name=DEFAULT_CONVERSATION_NAME,
        site_id="plasmodb",
    )
    session.graph.record_type = "transcript"
    session.sync_state = WDKSyncState()

    await apply_and_commit(
        deps=StrategyMutationContext(
            site_id="plasmodb",
            strategy_session=session,
            conversation_id=threads.conversation.id,
            user_prompt=_REQUEST,
        ),
        op=ReplaceStrategyOp(root=leaf("step_a")),
    )

    assert [c.kwargs["name"] for c in api.named("create_strategy")] == [_PROVISIONAL]
    assert (threads.conversation.name, threads.ast_name) == ("", _PROVISIONAL)

    title_write = await name_if_unnamed(threads, threads.conversation.id, title=_TITLE)
    assert title_write.named is not None
    await naming.put_the_name_on_wdk(title_write.named)

    assert (
        threads.conversation.name,
        threads.ast_name,
        sets.held["gs-1"].name,
        api.named("update_strategy")[-1].kwargs["name"],
    ) == (_TITLE, _TITLE, _TITLE, _TITLE)
