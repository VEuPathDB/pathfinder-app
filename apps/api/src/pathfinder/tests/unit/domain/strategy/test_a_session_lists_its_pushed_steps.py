"""A session lists the WDK ids of the steps it pushed, each once and in order."""

from __future__ import annotations

from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState


def test_the_pushed_steps_are_listed_once_in_order() -> None:
    session = StrategySession(site_id="plasmodb")
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_a": 441350023, "step_b": 440649693, "step_c": 441350023},
        wdk_strategy_id=42,
    )

    assert session.wdk_step_ids() == [440649693, 441350023]


def test_a_session_that_pushed_nothing_lists_no_step() -> None:
    assert StrategySession(site_id="plasmodb").wdk_step_ids() == []
