"""A gold strategy whose result is above the cap leaves no strategy on the site."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from veupathdb.wdk import StrategyAPI, WDKAnswer, WDKIdentifier

from pathfinder.platform.config import get_settings
from pathfinder.services import eval as gold
from pathfinder.services.experiment import materialization
from pathfinder.services.gene_sets.step_genes import TooManyGenesError

_STEP = 5001
_STRATEGY = 9001


async def test_a_gold_strategy_above_the_cap_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    total = get_settings().step_genes_cap + 1
    api = Mock(spec=StrategyAPI)
    api.create_step = AsyncMock(return_value=WDKIdentifier(id=_STEP))
    api.create_strategy = AsyncMock(return_value=WDKIdentifier(id=_STRATEGY))
    api.delete_strategy = AsyncMock(return_value=None)
    api.find_step = AsyncMock(return_value=Mock(record_class_name="transcript"))
    api.get_step_answer = AsyncMock(
        return_value=WDKAnswer.model_validate(
            {
                "meta": {"totalCount": total, "displayViewTotalCount": total},
                "records": [{"id": [{"name": "source_id", "value": "PF3D7_0100100"}]}],
            }
        )
    )
    monkeypatch.setattr(gold, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(materialization, "get_strategy_api", lambda _site: api)

    with pytest.raises(TooManyGenesError):
        await gold.build_gold_strategy(
            gold_id="gold-1",
            site_id="plasmodb",
            step_tree={"id": "step_a", "searchName": "GenesByTaxon", "parameters": {}},
        )

    api.delete_strategy.assert_awaited_once_with(_STRATEGY)
