"""The chat turn and the worker read one strategy row through one parse.

Chat turns run in the worker, so a parse the assistant spec owns alone would
never reach a user. Both callers go through ``persisted_graph``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.spec import TurnContextRequest

from pathfinder.assistants import pathfinder_spec
from pathfinder.jobs import runtime
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.platform.errors import ErrorCode, StrategyAstCorruptError
from pathfinder.services.strategies import session_factory

_SITE = "plasmodb"
_CONVERSATION_ID = UUID("4f69357c-0000-4000-8000-000000000001")

_STRATEGY_AST: dict[str, Any] = {
    "recordType": "transcript",
    "name": "kinases",
    "root": {
        "id": "step_root",
        "searchName": "GenesByMolecularWeight",
        "parameters": {
            "min_molecular_weight": {"type": "number", "value": 1000},
        },
    },
    "stepCounts": {"step_root": 2122},
    "wdkStepIds": {"step_root": 990001},
}

_CORRUPT_AST: dict[str, Any] = {"root": "not-a-node"}


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _conversation() -> Conversation:
    return Conversation(
        id=_CONVERSATION_ID,
        user_id=uuid4(),
        site_id=_SITE,
        name="kinases",
    )


def _install(monkeypatch: pytest.MonkeyPatch, strategy_ast: dict[str, Any]) -> None:
    """Serve the same row to the assistant spec and to the worker."""
    conversation = _conversation()
    strategy = ConversationStrategyView(strategy_ast=strategy_ast)

    class _Repo:
        def __init__(self, _session: _Session) -> None:
            return None

        async def get_strategy(
            self, _conversation_id: UUID
        ) -> ConversationStrategyView:
            return strategy

        async def get_with_strategy(
            self, _conversation_id: UUID
        ) -> tuple[Conversation, ConversationStrategyView]:
            return conversation, strategy

    for module in (pathfinder_spec, runtime):
        monkeypatch.setattr(module, "async_session_factory", _Session)
        monkeypatch.setattr(module, "ConversationRepository", _Repo)


def _turn_request() -> TurnContextRequest:
    return TurnContextRequest(
        conversation=_conversation(),
        site_id=_SITE,
        user_id=uuid4(),
        memory_store=None,
        cancel_event=asyncio.Event(),
        phase_models={},
        phase_reasoning={},
    )


async def test_both_callers_build_the_same_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One row, one parse: the chat turn and the worker see the same graph."""
    _install(monkeypatch, _STRATEGY_AST)

    from_spec = await pathfinder_spec.build_turn_context(_turn_request())
    from_worker = await runtime.build_worker_runtime_context(
        conversation_id=_CONVERSATION_ID,
        memory_store=None,
    )

    spec_graph = from_spec.strategy_session.get_graph(None)
    worker_graph = from_worker.strategy_session.get_graph(None)
    assert spec_graph is not None
    assert worker_graph is not None
    assert spec_graph.to_strategy_ast() == worker_graph.to_strategy_ast()
    assert sorted(spec_graph.steps) == ["step_root"]
    spec_sync = from_spec.strategy_session.sync_state
    worker_sync = from_worker.strategy_session.sync_state
    assert spec_sync is not None
    assert worker_sync is not None
    assert spec_sync.step_counts == {"step_root": 2122}
    assert worker_sync.step_counts == spec_sync.step_counts
    assert worker_sync.wdk_step_ids == {"step_root": 990001}


async def _spec_context() -> None:
    await pathfinder_spec.build_turn_context(_turn_request())


async def _worker_context() -> None:
    await runtime.build_worker_runtime_context(
        conversation_id=_CONVERSATION_ID,
        memory_store=None,
    )


@pytest.mark.parametrize("caller", [_spec_context, _worker_context])
async def test_a_corrupt_row_stops_both_callers_by_name(
    monkeypatch: pytest.MonkeyPatch,
    caller: Callable[[], Awaitable[None]],
) -> None:
    """Neither caller answers a corrupt row with an empty strategy."""
    _install(monkeypatch, _CORRUPT_AST)

    with pytest.raises(StrategyAstCorruptError) as excinfo:
        await caller()

    assert excinfo.value.code is ErrorCode.STRATEGY_AST_CORRUPT
    assert str(_CONVERSATION_ID) in (excinfo.value.detail or "")


def _module_attr(module: ModuleType, name: str) -> object:
    """The object a module holds under a name, re-exported or not."""
    return getattr(module, name)


def test_the_row_to_session_parse_has_one_owner() -> None:
    """Only ``persisted_graph`` turns a stored row into a graph."""
    owner = session_factory.persisted_graph
    assert _module_attr(pathfinder_spec, "persisted_graph") is owner
    assert _module_attr(runtime, "persisted_graph") is owner
