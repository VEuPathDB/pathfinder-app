"""What this application asks the library for when it counts a plan."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.platform.identity import STEP_COUNTS_STRATEGY_NAME
from pathfinder.services.strategies import wdk_counts


def _plan(step_id: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id=step_id,
            search_name="GenesByTaxon",
            parameters={"organism": StringValue(value="Pf3D7")},
        ),
    )


@pytest.fixture(autouse=True)
def _empty_cache() -> None:
    wdk_counts._STEP_COUNTS_CACHE.clear()


async def test_the_temporary_strategy_carries_this_products_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The library default names no product, so the caller names its own."""
    seen: list[str] = []

    async def _counts(
        payload: StrategyAst, site_id: str, *, strategy_name: str
    ) -> dict[str, int | None]:
        del payload, site_id
        seen.append(strategy_name)
        return {"s1": 41}

    monkeypatch.setattr(wdk_counts, "compute_plan_step_counts", _counts)

    counts = await wdk_counts.compute_step_counts_for_plan(_plan("s1"), "plasmodb")

    assert seen == [STEP_COUNTS_STRATEGY_NAME]
    assert counts == {"s1": 41}


async def test_the_same_plan_is_counted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def _counts(
        payload: StrategyAst, site_id: str, *, strategy_name: str
    ) -> dict[str, int | None]:
        del payload, site_id, strategy_name
        nonlocal calls
        calls += 1
        return {"s1": 7}

    monkeypatch.setattr(wdk_counts, "compute_plan_step_counts", _counts)

    first = await wdk_counts.compute_step_counts_for_plan(_plan("s1"), "plasmodb")
    second = await wdk_counts.compute_step_counts_for_plan(_plan("s1"), "plasmodb")

    assert calls == 1
    assert first == {"s1": 7}
    assert second == {"s1": 7}


async def test_a_different_plan_is_counted_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counted: list[str] = []

    async def _counts(
        payload: StrategyAst, site_id: str, *, strategy_name: str
    ) -> dict[str, int | None]:
        del site_id, strategy_name
        counted.append(payload.root.id)
        return {payload.root.id: 3}

    monkeypatch.setattr(wdk_counts, "compute_plan_step_counts", _counts)

    await wdk_counts.compute_step_counts_for_plan(_plan("s1"), "plasmodb")
    await wdk_counts.compute_step_counts_for_plan(_plan("s2"), "plasmodb")

    assert counted == ["s1", "s2"]
