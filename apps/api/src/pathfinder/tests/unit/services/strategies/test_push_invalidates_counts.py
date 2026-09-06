"""Pushing a step to WDK invalidates its cached result count.

A parameter edit changes what the step returns, so the previously stored
count is wrong the instant the push succeeds. Keeping it produced the UAT
bug where the agent reported 2,862 genes for a strategy that returned 587:
the UI recomputes counts on its own endpoint and looked right, while the
persisted count (which the agent reads) stayed at the pre-edit value.

``None`` means "unknown, go recompute" — every consumer already handles it.
"""

from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.services.strategies.wdk_counts import invalidate_counts_for


def _state() -> WDKSyncState:
    state = WDKSyncState()
    state.step_counts = {"a": 2862, "b": 100}
    return state


def test_pushed_step_count_becomes_unknown() -> None:
    state = _state()
    invalidate_counts_for(state, ["a"])
    assert state.step_counts["a"] is None


def test_untouched_steps_keep_their_counts() -> None:
    state = _state()
    invalidate_counts_for(state, ["a"])
    assert state.step_counts["b"] == 100


def test_invalidating_many_steps() -> None:
    state = _state()
    invalidate_counts_for(state, ["a", "b"])
    assert state.step_counts == {"a": None, "b": None}


def test_empty_push_changes_nothing() -> None:
    state = _state()
    invalidate_counts_for(state, [])
    assert state.step_counts == {"a": 2862, "b": 100}


def test_unknown_step_id_is_ignored() -> None:
    # A step that was never counted must not gain a phantom entry.
    state = _state()
    invalidate_counts_for(state, ["never-seen"])
    assert "never-seen" not in state.step_counts
