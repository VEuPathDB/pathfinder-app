from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.strategy import StrategyAst
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStrategyDetails
from veupathdb_mcp.wdk import WireStep, build_snapshot_from_wdk

from strategist.domain.unread import Unread
from strategist.services.strategies import reconcile
from strategist.services.strategies.commit import apply_and_commit
from strategist.services.strategies.reconcile import held_by_id
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests.unit.services.strategies.test_a_commit_leaves_wdks_counts import (
    _rebind_text,
    _seeded_session,
    _StubAPI,
    wdk,
)

_UNPARSED = WDKError(
    "the step tree names a step the strategy does not hold", status=200
)
_NOT_READ = Unread(
    reason=(
        "the strategy did not read back: HTTP 200: VEuPathDB service error: the step "
        "tree names a step the strategy does not hold"
    )
)

__all__ = ["wdk"]


def _does_not_parse(_live: WDKStrategyDetails) -> NoReturn:
    raise _UNPARSED


def test_a_read_back_that_does_not_parse_is_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reconcile, "build_snapshot_from_wdk", _does_not_parse)
    live = WDKStrategyDetails.model_validate(
        {
            "strategyId": 1,
            "name": "s",
            "rootStepId": 10,
            "recordClassName": "transcript",
            "stepTree": {"stepId": 10},
            "steps": {},
        }
    )

    held = held_by_id(live, WDKSyncState(wdk_strategy_id=1, wdk_step_ids={"a": 10}))

    assert held == _NOT_READ


async def test_a_commit_whose_read_back_does_not_parse_names_it(
    monkeypatch: pytest.MonkeyPatch, wdk: _StubAPI
) -> None:
    reads: list[WDKStrategyDetails] = []

    def _parses_before_the_push(
        live: WDKStrategyDetails,
    ) -> tuple[StrategyAst, dict[str, WireStep]]:
        reads.append(live)
        if len(reads) > 1:
            raise _UNPARSED
        return build_snapshot_from_wdk(live)

    monkeypatch.setattr(reconcile, "build_snapshot_from_wdk", _parses_before_the_push)
    deps = _seeded_session()

    await apply_and_commit(deps=deps, op=_rebind_text())

    assert ensure_sync_state(deps.strategy_session).strategy_not_read == _NOT_READ
