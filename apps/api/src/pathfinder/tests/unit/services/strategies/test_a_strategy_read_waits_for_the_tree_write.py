from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStep

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.gene_sets import strategy_genes
from pathfinder.services.gene_sets.homes import StepGenes
from pathfinder.services.gene_sets.strategy_genes import read_strategy_genes
from pathfinder.services.strategies import sync
from pathfinder.services.strategies.sync import (
    TreeNotHeldError,
    sync_strategy_for_site,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.read_saves_back import (
    AFTER_THE_DELETE,
    BEFORE_THE_DELETE,
    GO,
    INNER,
    STRATEGY,
    TEXT,
    ReadSavesBack,
    one_request_per_strategy,
    strategy_api_on,
)


def _graph_after_the_delete() -> StrategyGraph:
    graph = StrategyGraph("g1", "Signal peptide kinases", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="inner",
            search_name="__combine__",
            primary_input=StrategyStepNode(id="text", search_name="GenesByText"),
            secondary_input=StrategyStepNode(id="go", search_name="GenesByGoTerm"),
            operator=CombineOp.INTERSECT,
        )
    )
    for step in graph.steps.values():
        step.record_class = "transcript"
    graph.recompute_roots()
    return graph


def _held_before_the_delete() -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids={"text": TEXT, "go": GO, "inner": INNER},
        wdk_strategy_id=STRATEGY,
        wdk_step_tree=BEFORE_THE_DELETE,
        wdk_strategy_name="Signal peptide kinases",
    )


@pytest.fixture
def signed_in() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
async def site(monkeypatch: pytest.MonkeyPatch, signed_in: None) -> ReadSavesBack:
    del signed_in
    served = ReadSavesBack()
    api = await strategy_api_on(served)
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(strategy_genes, "get_strategy_api", lambda _site_id: api)

    async def _genes(_site_id: str, _root: WDKStep) -> StepGenes:
        return StepGenes(
            gene_ids=["PF3D7_0102200"], homes={}, record_class="transcript"
        )

    monkeypatch.setattr(strategy_genes, "read_genes_of", _genes)
    return served


async def _a_read_during_the_delete(site: ReadSavesBack) -> None:
    save = asyncio.create_task(
        sync_strategy_for_site(
            graph=_graph_after_the_delete(),
            sync_state=_held_before_the_delete(),
            site_id="plasmodb",
        )
    )
    await site.put_started.wait()
    refresh = asyncio.create_task(read_strategy_genes("plasmodb", STRATEGY))
    await asyncio.gather(save, refresh)


async def test_without_a_line_the_read_restores_the_old_tree(
    site: ReadSavesBack,
) -> None:
    await _a_read_during_the_delete(site)

    assert site.held == BEFORE_THE_DELETE


async def test_in_the_line_the_read_leaves_the_written_tree(
    site: ReadSavesBack,
) -> None:
    with one_request_per_strategy():
        await _a_read_during_the_delete(site)

    assert site.held == AFTER_THE_DELETE


async def test_a_tree_the_site_does_not_hold_after_the_write_fails_the_push(
    site: ReadSavesBack,
) -> None:
    site.reverted = True
    state = _held_before_the_delete()

    with pytest.raises(TreeNotHeldError, match="root step 227283450 over 5 steps"):
        await sync_strategy_for_site(
            graph=_graph_after_the_delete(), sync_state=state, site_id="plasmodb"
        )

    assert state.wdk_step_tree == BEFORE_THE_DELETE
