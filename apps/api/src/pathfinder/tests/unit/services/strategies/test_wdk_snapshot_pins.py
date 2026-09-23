"""The step ids and the name the read of a live WDK strategy keeps.

The fixture is the shape WDK returns for a saved strategy: a combine over a
transform, plus a combine WDK marks as an expanded saved sub-strategy.
"""

from __future__ import annotations

import pytest
from veupathdb.wdk import (
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)

from pathfinder.services.strategies import reconcile
from pathfinder.services.strategies.reconcile import reconcile_sync_state_with_wdk
from pathfinder.services.strategies.sync_state import WDKSyncState

_BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


class _FakeAPI:
    """Answers one strategy read."""

    def __init__(self, details: WDKStrategyDetails) -> None:
        self._details = details

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        del strategy_id
        return self._details


def _step(
    step_id: int,
    search_name: str,
    parameters: dict[str, str] | None = None,
    **extra: object,
) -> WDKStep:
    return WDKStep.model_validate(
        {
            "id": step_id,
            "search_name": search_name,
            "search_config": WDKSearchConfig(parameters=parameters or {}),
            "custom_name": f"name-{step_id}",
            **extra,
        }
    )


def _tree() -> WDKStepTree:
    return WDKStepTree(
        step_id=40,
        primary_input=WDKStepTree(step_id=30, primary_input=WDKStepTree(step_id=10)),
        secondary_input=WDKStepTree(step_id=20),
    )


def _details() -> WDKStrategyDetails:
    return WDKStrategyDetails(
        strategy_id=7,
        name="kinases",
        root_step_id=40,
        record_class_name="transcript",
        step_tree=_tree(),
        steps={
            "10": _step(
                10, "GenesByText", {"text_expression": "kinase"}, estimated_size=5
            ),
            "20": _step(20, "GenesByTaxon", strategy_id=99, estimated_size=7),
            "30": _step(30, "GenesByOrthologs", estimated_size=3),
            "40": _step(
                40,
                _BOOLEAN,
                {"bq_operator": "INTERSECT"},
                expanded=True,
                expanded_name="saved-1",
                estimated_size=2,
            ),
        },
    )


async def _reconciled(
    monkeypatch: pytest.MonkeyPatch,
    details: WDKStrategyDetails,
    held: dict[str, int],
) -> WDKSyncState:
    monkeypatch.setattr(
        reconcile, "get_strategy_api", lambda site_id: _FakeAPI(details)
    )
    state = WDKSyncState(wdk_step_ids=dict(held), wdk_strategy_id=7)
    await reconcile_sync_state_with_wdk(state, "plasmodb", 7)
    return state


class TestTheLiveStepIds:
    async def test_every_node_of_the_tree_is_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        held = {"a": 10, "b": 20, "c": 30, "d": 40, "gone": 99}

        state = await _reconciled(monkeypatch, _details(), held)

        assert state.wdk_step_ids == {"a": 10, "b": 20, "c": 30, "d": 40}
        assert state.wdk_strategy_name == "kinases"

    async def test_a_leaf_tree_keeps_one_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        details = _details().model_copy(update={"step_tree": WDKStepTree(step_id=5)})

        state = await _reconciled(monkeypatch, details, {"a": 5, "b": 10})

        assert state.wdk_step_ids == {"a": 5}
