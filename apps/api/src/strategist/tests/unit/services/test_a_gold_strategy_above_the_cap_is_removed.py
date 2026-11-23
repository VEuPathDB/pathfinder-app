"""A gold strategy whose result is above the cap leaves no strategy on the site."""

from __future__ import annotations

import pytest
from veupathdb.wdk import StrategyAPI

from strategist.platform.config import get_settings
from strategist.services.eval import build_gold_strategy
from strategist.services.gene_sets.step_genes import TooManyGenesError
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
)


async def test_a_gold_strategy_above_the_cap_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    cap = get_settings().step_genes_cap

    async def _too_many(_api: StrategyAPI, _root_step_id: int) -> list[str]:
        raise TooManyGenesError(cap + 1, cap)

    monkeypatch.setattr("strategist.services.eval.fetch_all_gene_ids", _too_many)

    with pytest.raises(TooManyGenesError):
        await build_gold_strategy(
            gold_id="gold-1",
            site_id="plasmodb",
            step_tree={"id": "step_a", "searchName": "GenesByTaxon", "parameters": {}},
        )

    assert (len(env.wdk.written("POST", "/strategies")), env.wdk.strategies) == (1, {})
