from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, flatten_tree

from strategist.services.strategies.reconcile import reconcile_sync_state_with_wdk
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.recording_wdk import RecordingWDK
from strategist.tests.unit.ai.tools._strategy_edit_stubs import combine, leaf


async def test_a_combine_outside_the_live_tree_is_read_with_its_operator() -> None:
    api = RecordingWDK()
    steps = flatten_tree(
        combine("step_join", leaf("step_a"), leaf("step_b"), CombineOp.MINUS)
    )
    sync_state = WDKSyncState(wdk_step_ids={"step_join": 7, "step_a": 5, "step_b": 6})
    api.holds(steps, sync_state)

    held = await reconcile_sync_state_with_wdk(sync_state, api)

    assert (held["step_join"].operator, held["step_a"].operator) == (
        CombineOp.MINUS,
        None,
    )
