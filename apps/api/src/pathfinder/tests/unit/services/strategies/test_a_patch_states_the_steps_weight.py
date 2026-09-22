"""A search-config patch states the step's weight when the graph holds one."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.wdk import StrategyAPI, WDKSearchConfig

from pathfinder.services.strategies._wdk_step_calls import _update_existing_step
from pathfinder.services.strategies.sync_state import WDKSyncState


def _step(weight: int | None) -> StrategyStep:
    return StrategyStep(
        id="step_a",
        kind=StepKind.SEARCH,
        search_name="GenesByTaxon",
        wdk_weight=weight,
    )


async def _patch(
    monkeypatch: pytest.MonkeyPatch, step: StrategyStep
) -> WDKSearchConfig:
    sent: list[WDKSearchConfig] = []

    async def record(**kwargs: Any) -> None:
        sent.append(kwargs["search_config"])

    api = StrategyAPI.__new__(StrategyAPI)
    monkeypatch.setattr(api, "update_step_search_config", record)
    await _update_existing_step(
        api,
        WDKSyncState(wdk_step_ids={"step_a": 7}),
        step,
        "transcript",
        name_moved=False,
    )
    return sent[0]


@pytest.mark.parametrize("weight", [3, 0])
async def test_a_held_weight_is_stated(
    monkeypatch: pytest.MonkeyPatch, weight: int
) -> None:
    config = await _patch(monkeypatch, _step(weight))

    assert (config.wdk_weight, "wdk_weight" in config.model_fields_set) == (
        weight,
        True,
    )


async def test_no_weight_leaves_the_steps_own_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = await _patch(monkeypatch, _step(None))

    assert sorted(config.model_fields_set) == ["parameters"]
