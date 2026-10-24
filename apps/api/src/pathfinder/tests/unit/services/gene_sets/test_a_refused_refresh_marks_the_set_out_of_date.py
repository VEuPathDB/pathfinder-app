from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.homes import StepGenes
from pathfinder.services.gene_sets.operations import EmptyResyncError, GeneSetService
from pathfinder.services.gene_sets.step_genes import TooManyGenesError
from pathfinder.services.gene_sets.strategy_genes import (
    RecordsAreNotGenesError,
    StrategyGenes,
)
from pathfinder.services.gene_sets.types import (
    GeneSet,
    OutOfDate,
    ResultAboveTheCap,
    ResultNotGenes,
    ResultWithoutGenes,
    StrategyRootContext,
)
from pathfinder.tests._support.gene_set_store import InMemoryGeneSetStore

_STRATEGY = 214_645_070
_HELD = ["PF3D7_0103400.1-p1", "TGME49_200010-t26_1-p1"]


async def _store_holding(out_of_date: OutOfDate | None) -> InMemoryGeneSetStore:
    store = InMemoryGeneSetStore()
    await store.save(
        GeneSet(
            id="g1",
            name="singletons",
            site_id="orthomcl",
            gene_ids=list(_HELD),
            source="strategy",
            wdk_strategy_id=_STRATEGY,
            record_type="sequence",
            answer_revision="0a1b2c3d4e5f6071",
            out_of_date=out_of_date,
        )
    )
    return store


async def _resync(store: InMemoryGeneSetStore) -> GeneSet | None:
    return await GeneSetService(store).resync_strategy(
        "g1",
        wdk_strategy_id=_STRATEGY,
        site_id="orthomcl",
        answer_revision="9f1c2b7a4e3d5c60",
    )


def _answering(gene_ids: list[str]) -> Callable[..., Awaitable[StrategyGenes]]:
    async def _read(site_id: str, wdk_strategy_id: int) -> StrategyGenes:
        del site_id
        return StrategyGenes(
            genes=StepGenes(gene_ids=gene_ids, homes={}, record_class="sequence"),
            context=StrategyRootContext(
                wdk_strategy_id=wdk_strategy_id,
                wdk_step_id=227284190,
                search_name=None,
                record_type="sequence",
                parameters=None,
            ),
            step_count=2,
        )

    return _read


def _refusing(error: Exception) -> Callable[..., Awaitable[StrategyGenes]]:
    async def _read(*_args: object, **_kwargs: object) -> StrategyGenes:
        raise error

    return _read


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            TooManyGenesError(309_068, 10_000),
            ResultAboveTheCap(count=309_068, cap=10_000),
        ),
        (RecordsAreNotGenesError("group"), ResultNotGenes(record_class="group")),
    ],
)
async def test_a_refused_root_keeps_the_genes_and_records_why(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: OutOfDate
) -> None:
    monkeypatch.setattr(operations, "read_strategy_genes", _refusing(error))
    store = await _store_holding(None)

    with pytest.raises(type(error)):
        await _resync(store)

    held = store.rows["g1"]
    assert (held.gene_ids, held.answer_revision, held.out_of_date) == (
        _HELD,
        "0a1b2c3d4e5f6071",
        reason,
    )


async def test_a_root_that_returns_no_genes_keeps_the_genes_and_records_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations, "read_strategy_genes", _answering([]))
    store = await _store_holding(None)

    with pytest.raises(EmptyResyncError):
        await _resync(store)

    held = store.rows["g1"]
    assert (held.gene_ids, held.answer_revision, held.out_of_date) == (
        _HELD,
        "0a1b2c3d4e5f6071",
        ResultWithoutGenes(),
    )


@pytest.mark.parametrize(
    "held_reason",
    [
        ResultAboveTheCap(count=309_068, cap=10_000),
        ResultNotGenes(record_class="group"),
        ResultWithoutGenes(),
    ],
)
async def test_a_root_that_returns_genes_clears_the_record(
    monkeypatch: pytest.MonkeyPatch, held_reason: OutOfDate
) -> None:
    monkeypatch.setattr(
        operations, "read_strategy_genes", _answering(["PF3D7_0103400.1-p1"])
    )
    store = await _store_holding(held_reason)

    await _resync(store)

    held = store.rows["g1"]
    assert (held.gene_ids, held.answer_revision, held.out_of_date) == (
        ["PF3D7_0103400.1-p1"],
        "9f1c2b7a4e3d5c60",
        None,
    )
