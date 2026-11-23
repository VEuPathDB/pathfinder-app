"""A search-config patch states the step's weight, and 0 when it holds none."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import StepKind, StepSettings, StrategyStep
from veupathdb.wdk import StrategyAPI, WDKSearchConfig

from strategist.services.strategies._wdk_step_calls import _put_search_config
from strategist.services.strategies.sync_state import WDKSyncState


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
    await _put_search_config(
        api,
        WDKSyncState(wdk_step_ids={"step_a": 7}),
        step,
        "transcript",
        step.parameters,
        StepSettings(),
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


async def test_no_weight_clears_the_one_the_step_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = await _patch(monkeypatch, _step(None))

    assert (config.wdk_weight, sorted(config.model_fields_set)) == (
        0,
        ["parameters", "wdk_weight"],
    )
