from __future__ import annotations

from typing import NoReturn, cast

from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyAPI

from strategist.domain.unread import Unread
from strategist.services.strategies._tree_write import read_the_strategy
from strategist.services.strategies.commit_tree import CommittedTree
from strategist.services.strategies.spec_build import outcome_of
from strategist.services.strategies.sync_state import WDKSyncState

_NOT_READ = Unread(reason="HTTP 503: VEuPathDB service error: Service Unavailable")
_UNAVAILABLE = WDKError("Service Unavailable", status=503)


class _Unanswering:
    async def get_strategy(self, strategy_id: int) -> NoReturn:
        del strategy_id
        raise _UNAVAILABLE


def _held() -> WDKSyncState:
    return WDKSyncState(
        wdk_strategy_id=900,
        wdk_step_ids={"step_a": 11, "step_b": 12},
        step_counts={"step_a": 152, "step_b": 0},
    )


async def test_a_read_back_that_failed_is_named_on_the_sync_state() -> None:
    sync_state = _held()

    read = await read_the_strategy(cast("StrategyAPI", _Unanswering()), sync_state)

    assert read == _NOT_READ
    assert (sync_state.step_counts, sync_state.strategy_not_read) == (
        {"step_a": 152, "step_b": 0},
        _NOT_READ,
    )


async def test_the_build_outcome_names_the_read_back_that_failed() -> None:
    sync_state = _held()
    await read_the_strategy(cast("StrategyAPI", _Unanswering()), sync_state)

    outcome = outcome_of(
        CommittedTree(pushed=["step_a", "step_b"], put=True),
        {},
        sync_state,
        nodes=[],
        change=None,
    )

    assert (outcome.not_read, outcome.zero_step_ids) == (_NOT_READ, ["step_b"])
