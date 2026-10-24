from __future__ import annotations

import pytest
from veupathdb.wdk import WDKStep, WDKStrategyDetails

from pathfinder.services.gene_sets import strategy_genes
from pathfinder.services.gene_sets.homes import StepGenes
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.strategy_genes import RecordsAreNotGenesError
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.tests._support.gene_set_store import InMemoryGeneSetStore

_STRATEGY = 214645080
_ROOT = 227284200


class _Site:
    def __init__(self, root_class: str = "transcript") -> None:
        self.root_class = root_class

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": "exported proteins",
                "rootStepId": _ROOT,
                "recordClassName": "transcript",
                "stepTree": {"stepId": _ROOT},
                "steps": {
                    str(_ROOT): {
                        "id": _ROOT,
                        "searchName": "GenesByExportPred",
                        "searchConfig": {"parameters": {}},
                        "recordClassName": self.root_class,
                        "estimatedSize": 1,
                    }
                },
            }
        )


async def _genes(_site_id: str, _step: WDKStep) -> StepGenes:
    return StepGenes(gene_ids=["PF3D7_0103400.1"], homes={}, record_class="transcript")


async def test_a_refreshed_set_takes_the_class_wdk_states_for_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(strategy_genes, "get_strategy_api", lambda _site: _Site())
    monkeypatch.setattr(strategy_genes, "read_genes_of", _genes)
    store = InMemoryGeneSetStore()
    await store.save(
        GeneSet(
            id="g1",
            name="exported",
            site_id="plasmodb",
            gene_ids=["PF3D7_0103400.1"],
            source="strategy",
            wdk_strategy_id=_STRATEGY,
            record_type="gene",
        )
    )

    refreshed = await GeneSetService(store).resync_strategy(
        "g1",
        wdk_strategy_id=_STRATEGY,
        site_id="plasmodb",
        answer_revision="9f1c2b7a4e3d5c61",
    )

    assert refreshed is not None
    assert (refreshed.record_type, refreshed.search_name, refreshed.wdk_step_id) == (
        "transcript",
        "GenesByExportPred",
        _ROOT,
    )


async def test_a_root_step_of_groups_is_refused_by_the_class_wdk_states_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        strategy_genes, "get_strategy_api", lambda _site: _Site(root_class="group")
    )
    monkeypatch.setattr(strategy_genes, "read_genes_of", _genes)

    with pytest.raises(RecordsAreNotGenesError) as refused:
        await strategy_genes.read_strategy_genes("plasmodb", _STRATEGY)

    assert refused.value.record_class == "group"
