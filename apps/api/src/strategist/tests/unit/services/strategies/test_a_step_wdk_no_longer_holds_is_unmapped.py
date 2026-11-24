from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStrategyDetails

from strategist.services.strategies.reconcile import reconcile_sync_state_with_wdk
from strategist.services.strategies.sync_state import WDKSyncState

_GONE = WDKError("no such step", status=404)
_DOWN = WDKError("Service Unavailable", status=503)


class _Answering:
    def __init__(self, refusal: WDKError) -> None:
        self.refusal = refusal

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        del strategy_id
        raise AssertionError

    async def find_step(self, step_id: int) -> NoReturn:
        del step_id
        raise self.refusal


async def test_a_step_wdk_answers_404_for_is_unmapped() -> None:
    state = WDKSyncState(wdk_step_ids={"step_a": 77})

    held = await reconcile_sync_state_with_wdk(state, _Answering(_GONE))

    assert (held, state.wdk_step_ids) == ({}, {})


async def test_a_step_read_the_site_did_not_answer_raises() -> None:
    state = WDKSyncState(wdk_step_ids={"step_a": 77})

    with pytest.raises(WDKError) as refused:
        await reconcile_sync_state_with_wdk(state, _Answering(_DOWN))

    assert (refused.value.status, state.wdk_step_ids) == (503, {"step_a": 77})
