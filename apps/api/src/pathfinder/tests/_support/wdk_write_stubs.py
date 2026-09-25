"""Stand-ins for the catalog and WDK reads a strategy write makes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import commit, stated_sides, step_wdk_push
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_definitions,
    serve_recorded_record_types,
)


async def accepts_every_value(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """Answer a validation with the values as sent, in the catalog's shape."""
    return ValidatedParams(params=dict(kwargs["parameters"]), record_class="transcript")


async def no_plan_params(*_args: Any, **_kwargs: Any) -> set[str]:
    return set()


async def no_reconcile(*_args: Any, **_kwargs: Any) -> None:
    return None


def stub_every_catalog_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A write reaches no catalog and no WDK: every read answers its input."""
    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", no_plan_params)
    monkeypatch.setattr(stated_sides, "validate_parameters", accepts_every_value)
    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", no_reconcile)


def validate_against(
    monkeypatch: pytest.MonkeyPatch, definitions: Sequence[WDKSearch]
) -> None:
    """A write validates its values against these recorded definitions, and
    finds each record type in plasmodb's recorded listing."""
    serve_recorded_record_types(monkeypatch)
    serve_recorded_definitions(monkeypatch, definitions)


@dataclass
class RecordedPushes:
    """A strategy push that records the name and the request each one carries."""

    result: SyncResult
    pushed: list[tuple[str | None, str]] = field(default_factory=list)

    async def sync(
        self,
        *,
        graph: StrategyGraph,
        sync_state: WDKSyncState,
        site_id: str,
        strategy_name: str | None = None,
        user_prompt: str = "",
    ) -> SyncResult:
        del graph, sync_state, site_id
        self.pushed.append((strategy_name, user_prompt))
        return self.result


def landed_pushes(
    wdk_strategy_id: int,
    *,
    root_step_id: int = 0,
    root_count: int | None = None,
    step_count: int = 0,
) -> RecordedPushes:
    """Pushes that each land on ``wdk_strategy_id`` and report no step counts."""
    return RecordedPushes(
        result=SyncResult(
            wdk_strategy_id=wdk_strategy_id,
            wdk_url="http://test",
            root_step_id=root_step_id,
            counts={},
            root_count=root_count,
            zero_step_ids=[],
            step_count=step_count,
        )
    )
