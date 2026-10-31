from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.wdk import (
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
    walk_wdk_step_tree,
)

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

_STRATEGY = 214644620
_TEXT, _GO, _INNER, _SIGNAL, _OUTER = (
    227283340,
    227283350,
    227283440,
    227283370,
    227283450,
)
_BEFORE_THE_DELETE = WDKStepTree(
    step_id=_OUTER,
    primary_input=WDKStepTree(
        step_id=_INNER,
        primary_input=WDKStepTree(step_id=_TEXT),
        secondary_input=WDKStepTree(step_id=_GO),
    ),
    secondary_input=WDKStepTree(step_id=_SIGNAL),
)
_AFTER_THE_DELETE = WDKStepTree(
    step_id=_INNER,
    primary_input=WDKStepTree(step_id=_TEXT),
    secondary_input=WDKStepTree(step_id=_GO),
)
_PUT_WAITS_SECONDS = 0.5


class _ReadSavesBack:
    def __init__(self, held: WDKStepTree, *, reverted: bool = False) -> None:
        self.held = held
        self.reverted = reverted
        self.put_started = asyncio.Event()
        self.reader_loaded = asyncio.Event()
        self.put_landed = asyncio.Event()

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        loaded = self.held
        self.reader_loaded.set()
        await self.put_landed.wait()
        self.held = loaded
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="Signal peptide kinases",
            root_step_id=loaded.step_id,
            record_class_name="transcript",
            step_tree=loaded,
            steps={
                str(node.step_id): WDKStep(
                    id=node.step_id,
                    search_name="GenesByText",
                    search_config=WDKSearchConfig(parameters={}),
                    record_class_name="transcript",
                    estimated_size=48,
                )
                for node in walk_wdk_step_tree(loaded)
            },
        )

    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
        *,
        description: str | None = None,
    ) -> WDKStrategyDetails:
        del name, user_id, description
        if step_tree is not None:
            self.put_started.set()
            with suppress(TimeoutError):
                await asyncio.wait_for(self.reader_loaded.wait(), _PUT_WAITS_SECONDS)
            if not self.reverted:
                self.held = step_tree
            self.put_landed.set()
        return await self.get_strategy(strategy_id)


def _graph_after_the_delete() -> StrategyGraph:
    graph = StrategyGraph("g1", "Signal peptide kinases", "plasmodb")
    graph.record_type = "transcript"
    inner = StrategyStepNode(
        id="inner",
        search_name="__combine__",
        primary_input=StrategyStepNode(id="text", search_name="GenesByText"),
        secondary_input=StrategyStepNode(id="go", search_name="GenesByGoTerm"),
        operator=CombineOp.INTERSECT,
    )
    graph.steps = flatten_tree(inner)
    for step in graph.steps.values():
        step.record_class = "transcript"
    graph.recompute_roots()
    return graph


def _held_before_the_delete() -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids={"text": _TEXT, "go": _GO, "inner": _INNER},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=_BEFORE_THE_DELETE,
        wdk_strategy_name="Signal peptide kinases",
    )


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> _ReadSavesBack:
    wdk = _ReadSavesBack(_BEFORE_THE_DELETE)
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: wdk)
    monkeypatch.setattr(strategy_genes, "get_strategy_api", lambda _site_id: wdk)

    async def _genes(_site_id: str, _root: WDKStep) -> StepGenes:
        return StepGenes(
            gene_ids=["PF3D7_0102200"], homes={}, record_class="transcript"
        )

    monkeypatch.setattr(strategy_genes, "read_genes_of", _genes)
    return wdk


async def test_a_read_that_starts_during_the_tree_write_leaves_the_written_tree(
    site: _ReadSavesBack,
) -> None:
    save = asyncio.create_task(
        sync_strategy_for_site(
            graph=_graph_after_the_delete(),
            sync_state=_held_before_the_delete(),
            site_id="plasmodb",
        )
    )
    await site.put_started.wait()
    refresh = asyncio.create_task(read_strategy_genes("plasmodb", _STRATEGY))

    await asyncio.gather(save, refresh)

    assert site.held == _AFTER_THE_DELETE


async def test_a_tree_the_site_does_not_hold_after_the_write_fails_the_push(
    site: _ReadSavesBack,
) -> None:
    site.reverted = True
    state = _held_before_the_delete()

    with pytest.raises(TreeNotHeldError, match="root step 227283450 over 5 steps"):
        await sync_strategy_for_site(
            graph=_graph_after_the_delete(), sync_state=state, site_id="plasmodb"
        )

    assert state.wdk_step_tree == _BEFORE_THE_DELETE
