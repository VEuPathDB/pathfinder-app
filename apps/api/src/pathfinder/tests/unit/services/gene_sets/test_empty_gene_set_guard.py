"""Saving a gene set that resolved to zero genes is never the intent.

Observed in UAT: the workbench listed two 0-gene sets, auto-imported from
strategies that returned nothing. A 0-gene set is inert everywhere it is used
(enrichment has no input, set operations return empty, export writes a header
row) and reads as a real result in the list, so it costs the researcher a
click to discover it is worthless.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.errors import ValidationError

from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.homes import StepGenes
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.strategy_genes import StrategyGenes
from pathfinder.services.gene_sets.types import StrategyRootContext
from pathfinder.tests._support.gene_set_store import InMemoryGeneSetStore


def _stub_resolve(
    monkeypatch: pytest.MonkeyPatch,
    resolved: list[str],
) -> None:
    async def _fake(site_id: str, wdk_strategy_id: int) -> StrategyGenes:
        del site_id
        return StrategyGenes(
            genes=StepGenes(gene_ids=resolved, homes={}, record_class="transcript"),
            context=StrategyRootContext(
                wdk_strategy_id=wdk_strategy_id,
                wdk_step_id=439858930,
                search_name="GenesByTaxon",
                record_type="transcript",
                parameters={},
            ),
            step_count=1,
        )

    monkeypatch.setattr(operations, "read_strategy_genes", _fake)


async def test_creating_an_empty_gene_set_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_resolve(monkeypatch, [])
    store = InMemoryGeneSetStore()

    with pytest.raises(ValidationError) as excinfo:
        await GeneSetService(store).create_from_strategy(
            user_id=uuid4(),
            name="Gametocyte markers",
            site_id="plasmodb",
            wdk_strategy_id=330517023,
        )

    # The message must say what to do, not just that something failed.
    assert "0 genes" in str(excinfo.value.detail)
    assert store.rows == {}


async def test_a_resolved_gene_set_is_still_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_resolve(monkeypatch, ["PF3D7_0100100", "PF3D7_0100200"])
    store = InMemoryGeneSetStore()

    gs = await GeneSetService(store).create_from_strategy(
        user_id=uuid4(),
        name="Gametocyte markers",
        site_id="plasmodb",
        wdk_strategy_id=330517023,
    )

    assert gs.gene_ids == ["PF3D7_0100100", "PF3D7_0100200"]
