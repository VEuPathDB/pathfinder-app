"""The Lead renames the conversation's strategy through the rename the sidebar uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from assistant_core.platform.db import DBSessionFactory
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails

from pathfinder.ai.tools.standalone import strategy_rename
from pathfinder.ai.tools.standalone.strategy_rename import rename_strategy
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies import live_counts
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import leaf, session_with
from pathfinder.tests.unit.ai.tools.conftest import summary_of

_NAME = "UAT signal peptide screen"
_ROOT_WDK_ID = 900_001
_ROOT_COUNT = 116


@dataclass
class _Renames:
    """The rename service, recording each call and storing a suffixed name."""

    suffix: str = ""
    found: bool = True
    calls: list[tuple[UUID, str, DBSessionFactory]] = field(default_factory=list)

    async def __call__(
        self, conversation_id: UUID, name: str, *, session_factory: DBSessionFactory
    ) -> str | None:
        self.calls.append((conversation_id, name, session_factory))
        return f"{name}{self.suffix}" if self.found else None


def _site(count: int | None) -> StrategyAPI:
    api = Mock(spec=StrategyAPI)
    api.get_strategy = AsyncMock(
        return_value=WDKStrategyDetails.model_validate(
            {
                "strategyId": 42,
                "name": "Test",
                "rootStepId": _ROOT_WDK_ID,
                "stepTree": {"stepId": _ROOT_WDK_ID},
                "steps": {
                    str(_ROOT_WDK_ID): {
                        "id": _ROOT_WDK_ID,
                        "searchName": "GenesByTaxon",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": count,
                    }
                },
            }
        )
    )
    return api


@pytest.fixture
def renames(monkeypatch: pytest.MonkeyPatch) -> _Renames:
    held = _Renames()
    monkeypatch.setattr(strategy_rename, "rename_strategy_everywhere", held)
    return held


def _built() -> StrategySession:
    return session_with(leaf("step_a"), {"step_a": _ROOT_WDK_ID})


async def test_the_rename_names_the_thread_and_reports_the_root_count(
    monkeypatch: pytest.MonkeyPatch, renames: _Renames
) -> None:
    monkeypatch.setattr(
        live_counts, "get_strategy_api", lambda _site_id: _site(_ROOT_COUNT)
    )
    session = _built()
    ctx = lead_run_context(strategy_session=session, tool_call_id="call_1")

    returned = await rename_strategy(ctx, name=_NAME)

    assert renames.calls == [(ctx.deps.state.conversation_id, _NAME, no_database)]
    assert session.graph is not None
    assert session.graph.name == _NAME
    chunk = summary_of(returned)
    assert (chunk.data["summary"], chunk.data["status"]) == (
        f"{_NAME} - {_ROOT_COUNT} genes",
        "ok",
    )
    assert returned.return_value == (
        f"Renamed the strategy to {_NAME}. It returns {_ROOT_COUNT} genes."
    )
    metas = [
        chunk.data
        for chunk in returned.metadata or []
        if isinstance(chunk, DataChunk) and chunk.type == "data-strategy-meta"
    ]
    assert [(meta["name"], meta["strategyId"]) for meta in metas] == [(_NAME, "g1")]


async def test_the_graph_takes_the_name_the_store_kept(
    monkeypatch: pytest.MonkeyPatch, renames: _Renames
) -> None:
    monkeypatch.setattr(
        live_counts, "get_strategy_api", lambda _site_id: _site(_ROOT_COUNT)
    )
    renames.suffix = " (1)"
    session = _built()

    returned = await rename_strategy(lead_run_context(strategy_session=session), _NAME)

    assert session.graph is not None
    assert session.graph.name == f"{_NAME} (1)"
    assert returned.return_value == (
        f"Renamed the strategy to {_NAME} (1). It returns {_ROOT_COUNT} genes."
    )


async def test_a_count_the_site_does_not_answer_is_named_unknown(
    monkeypatch: pytest.MonkeyPatch, renames: _Renames
) -> None:
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda _site_id: _site(None))
    ctx = lead_run_context(strategy_session=_built(), tool_call_id="call_2")

    returned = await rename_strategy(ctx, name=_NAME)

    chunk = summary_of(returned)
    assert (chunk.data["summary"], chunk.data["status"]) == (
        f"{_NAME} - count not available",
        "warn",
    )
    assert returned.return_value == (
        f"Renamed the strategy to {_NAME}. The site gives no count for it now."
    )


async def test_a_conversation_with_no_step_is_refused_and_renames_nothing(
    renames: _Renames,
) -> None:
    with pytest.raises(ModelRetry, match="no strategy to rename"):
        await rename_strategy(lead_run_context(), name=_NAME)

    assert renames.calls == []


async def test_a_thread_the_store_does_not_hold_is_refused_and_keeps_its_name(
    monkeypatch: pytest.MonkeyPatch, renames: _Renames
) -> None:
    monkeypatch.setattr(
        live_counts, "get_strategy_api", lambda _site_id: _site(_ROOT_COUNT)
    )
    renames.found = False
    session = _built()

    with pytest.raises(ModelRetry, match="found no stored conversation"):
        await rename_strategy(lead_run_context(strategy_session=session), _NAME)

    assert session.graph is not None
    assert session.graph.name == "Test"
