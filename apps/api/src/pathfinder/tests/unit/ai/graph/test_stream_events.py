"""Every assistant turn is stamped with the strategy state it described.

Without the stamp a transcript reporting "2,862 transcripts at fold-change 1"
keeps reading as current after the threshold is edited to 2 and the strategy
returns 587. The stamp is the only thing the UI can compare against the live
revision to mark those numbers historical. It is PathFinder's turn epilogue,
so an assistant with no strategy emits nothing.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from pathfinder.ai.graph.stream_events import strategy_revision_event
from pathfinder.assistants import pathfinder_spec
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.persistence.models import ConversationStrategyView


def _ast(fold_change: str = "1") -> StrategyAst:
    return StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "root": {
                "id": "step_a",
                "searchName": "GenesByRNASeqEvidence",
                "parameters": {
                    "fold_change": {"type": "string", "value": fold_change},
                },
            },
        },
    )


def _strategy(ast: StrategyAst | None) -> ConversationStrategyView:
    return ConversationStrategyView(
        is_saved=False,
        step_count=1,
        gene_set_auto_imported=False,
        imported_saved_strategy_ids=[],
        estimated_size=None,
        strategy_ast=(
            ast.model_dump(by_alias=True, exclude_none=True, mode="json")
            if ast is not None
            else {}
        ),
    )


def _install_strategy(
    monkeypatch: pytest.MonkeyPatch,
    strategy: ConversationStrategyView,
) -> None:
    class _Session:
        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

    class _Repo:
        def __init__(self, _session: _Session) -> None:
            return None

        async def get_strategy(
            self, _conversation_id: UUID
        ) -> ConversationStrategyView:
            return strategy

    monkeypatch.setattr(pathfinder_spec, "async_session_factory", _Session)
    monkeypatch.setattr(pathfinder_spec, "ConversationRepository", _Repo)


def test_event_payload_carries_the_revision() -> None:
    chunk = strategy_revision_event(revision="abc123")
    assert chunk.type == "data-strategy-revision"
    assert chunk.data == {"revision": "abc123"}
    # Persisted, not transient: the stamp must survive a page reload.
    assert chunk.transient is not True


def test_the_epilogue_is_the_assistants_not_the_runtimes() -> None:
    assert (
        pathfinder_spec.build_pathfinder_spec().turn_epilogue
        is pathfinder_spec.strategy_revision_chunks
    )


async def test_turn_is_stamped_with_the_live_strategy_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_strategy(monkeypatch, _strategy(_ast("2")))

    chunks = await pathfinder_spec.strategy_revision_chunks(uuid4())

    assert chunks == (
        {
            "type": "data-strategy-revision",
            "data": {"revision": strategy_revision(_ast("2"))},
        },
    )


async def test_a_turn_with_no_strategy_is_not_stamped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_strategy(monkeypatch, _strategy(None))

    assert await pathfinder_spec.strategy_revision_chunks(uuid4()) == ()


async def test_a_missing_conversation_is_not_stamped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_strategy(monkeypatch, ConversationStrategyView())

    assert await pathfinder_spec.strategy_revision_chunks(uuid4()) == ()
