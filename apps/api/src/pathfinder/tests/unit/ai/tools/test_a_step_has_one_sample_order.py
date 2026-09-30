"""A step has one sample order: a read of its ids with a limit and a sample of
its records draw the same offsets while its answer is the same, and a read with
no limit keeps the site's order."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import (
    WDKAnswer,
    WDKFilterValue,
    WDKSearchConfig,
    WDKSortSpec,
    WDKStep,
)
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import results
from pathfinder.ai.tools.standalone.step_ids import StepGeneIds, read_step_ids
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.gene_sets import step_genes
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_WDK_STEP = 441126163
# The hostdb chromosome 17 location step of nine genes, in the site's order.
# The two turns name seven of them; a stand-in holds each place they do not.
_SITE_ORDER = [
    "ENSMUSG00000035929",
    "ENSMUSG00000060550",
    "ENSMUSG00000061232",
    "ENSMUSG00000067212",
    "ENSMUSG00000067235",
    "ENSMUSG00000073409",
    "unnamed_gene_6",
    "ENSMUSG00000079507",
    "unnamed_gene_8",
]


class _Step:
    """The location step's report, a page at a time."""

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByLocation",
            search_config=WDKSearchConfig(),
            record_class_name="transcript",
        )

    async def get_step_records(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        sorting: list[WDKSortSpec] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del step_id, attributes, tables, sorting, view_filters
        page = pagination or {}
        offset, wanted = page.get("offset", 0), page.get("numRecords", 0)
        return WDKAnswer.model_validate(
            {
                "meta": {"totalCount": len(_SITE_ORDER), "attributes": []},
                "records": [
                    {"displayName": g, "id": [{"name": "source_id", "value": g}]}
                    for g in _SITE_ORDER[offset : offset + wanted]
                ],
            }
        )


@pytest.fixture(autouse=True)
def _served(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(*_: object) -> list[str]:
        return []

    step = _Step()
    monkeypatch.setattr(results, "get_strategy_api", lambda _site_id: step)
    monkeypatch.setattr(step_genes, "get_strategy_api", lambda _site_id: step)
    monkeypatch.setattr(results, "sample_attributes", _none)


def _session() -> StrategySession:
    step = StrategyStepNode(
        id="step_loc",
        search_name="GenesByLocation",
        parameters={"organism": StringValue(value="Mus musculus C57BL/6J")},
    )
    graph = StrategyGraph(graph_id="g1", name="location", site_id="hostdb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(step)
    graph.recompute_roots()
    session = StrategySession(site_id="hostdb")
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"step_loc": _WDK_STEP})
    return session


async def test_five_ids_and_a_sample_of_five_are_the_same_five_genes() -> None:
    session = _session()
    sample = returned(
        await results.get_sample_records(
            agent_run_context(site_id="hostdb", strategy_session=session),
            _WDK_STEP,
            limit=5,
        ),
        SampleRecordsResult,
    )
    listed = returned(
        await read_step_ids(
            agent_run_context(site_id="hostdb", strategy_session=session),
            wdk_step_id=_WDK_STEP,
            limit=5,
        ),
        StepGeneIds,
    )

    assert (listed.gene_ids, listed.total, listed.complete) == (
        [str(r["id"]) for r in sample.records],
        9,
        False,
    )
    assert listed.gene_ids != _SITE_ORDER[:5]


async def test_a_read_with_no_limit_keeps_the_sites_order() -> None:
    listed = returned(
        await read_step_ids(
            agent_run_context(site_id="hostdb", strategy_session=_session()),
            wdk_step_id=_WDK_STEP,
        ),
        StepGeneIds,
    )

    assert (listed.gene_ids, listed.complete) == (_SITE_ORDER, True)
