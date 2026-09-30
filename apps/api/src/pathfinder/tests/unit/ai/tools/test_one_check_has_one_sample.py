"""An identical sample call answers the same records while the step's answer is
the same, in this message or a later one, so a re-read of them is the repeat the
record-read budget refuses by name and a later turn can show the sample again."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKAnswer, WDKFilterValue, WDKSortSpec, WDKStepTree
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import results
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_STEP_TOTAL = 1101
_MESSAGE = UUID("5e7c0c5a-4d7e-4d7a-9b8e-0a3f6c1d2e11")


class _Step:
    """A step of 1,101 genes whose record at offset n is gene n."""

    def __init__(self) -> None:
        self.read: list[int] = []

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
        del attributes, tables, sorting, view_filters
        self.read.append(step_id)
        page = pagination or {}
        offset, wanted = page.get("offset", 0), page.get("numRecords", 0)
        return WDKAnswer.model_validate(
            {
                "meta": {"displayTotalCount": _STEP_TOTAL, "attributes": []},
                "records": [
                    {
                        "displayName": f"ACA1_{gene:06d}",
                        "id": [{"name": "source_id", "value": f"ACA1_{gene:06d}"}],
                        "attributes": {},
                    }
                    for gene in range(offset, offset + wanted)
                ],
            }
        )


async def _sampled(step_id: int, message_id: UUID) -> list[str]:
    ctx = agent_run_context(site_id="amoebadb")
    ctx.deps.turn_markers.message_id = message_id
    result = await results.get_sample_records(ctx, step_id, limit=8)
    return [str(r["id"]) for r in returned(result, SampleRecordsResult).records]


@pytest.fixture(autouse=True)
def served(monkeypatch: pytest.MonkeyPatch) -> _Step:
    async def _none(*_: object) -> list[str]:
        return []

    step = _Step()
    monkeypatch.setattr(results, "get_strategy_api", lambda site_id: step)
    monkeypatch.setattr(results, "sample_attributes", _none)
    return step


async def test_a_sample_that_names_no_step_reads_the_root(served: _Step) -> None:
    session = StrategySession(site_id="amoebadb")
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_root": 441126163, "step_tm": 441126143},
        wdk_step_tree=WDKStepTree(
            step_id=441126163, primary_input=WDKStepTree(step_id=441126143)
        ),
    )
    ctx = agent_run_context(site_id="amoebadb", strategy_session=session)

    result = await results.get_sample_records(ctx, limit=8)

    assert returned(result, SampleRecordsResult).step_id == 441126163
    assert set(served.read) == {441126163}
    listings = ctx.deps.turn_markers.listings
    assert ({step: len(ids) for step, ids in listings.items()}) == {441126163: 8}


async def test_an_identical_sample_call_answers_the_same_genes() -> None:
    first = await _sampled(441126163, _MESSAGE)
    second = await _sampled(441126163, _MESSAGE)
    third = await _sampled(441126163, _MESSAGE)

    assert len(first) == 8
    assert second == first
    assert third == first


def test_the_offsets_are_drawn_from_the_seed_one_in_each_stride() -> None:
    seed = results.sample_seed(441126163, "")
    offsets = results.spread_offsets(_STEP_TOTAL, 8, seed=seed)

    assert offsets == results.spread_offsets(_STEP_TOTAL, 8, seed=seed)
    assert [o * 8 // _STEP_TOTAL for o in offsets] == list(range(8))


def test_another_step_or_another_answer_draws_its_own_offsets() -> None:
    held = results.spread_offsets(
        _STEP_TOTAL, 8, seed=results.sample_seed(441126163, "a1")
    )
    other_step = results.spread_offsets(
        _STEP_TOTAL, 8, seed=results.sample_seed(441126164, "a1")
    )
    other_answer = results.spread_offsets(
        _STEP_TOTAL, 8, seed=results.sample_seed(441126163, "a2")
    )

    assert (other_step != held, other_answer != held) == (True, True)


async def test_a_later_message_draws_the_same_sample_of_the_same_step() -> None:
    """The hostdb flow asks for the same five genes a turn later."""
    first = await _sampled(441126163, _MESSAGE)
    later = await _sampled(441126163, UUID(int=7))

    assert later == first


def _one_step_session(organism: str) -> StrategySession:
    step = StrategyStepNode(
        id="step_loc",
        search_name="GenesByLocation",
        parameters={"organism": StringValue(value=organism)},
    )
    graph = StrategyGraph(graph_id="g1", name="location", site_id="hostdb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(step)
    graph.recompute_roots()
    session = StrategySession(site_id="hostdb")
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"step_loc": 441126163})
    return session


async def test_a_step_whose_answer_changed_draws_another_sample() -> None:
    before = agent_run_context(
        site_id="hostdb", strategy_session=_one_step_session("Mus musculus C57BL/6J")
    )
    after = agent_run_context(
        site_id="hostdb", strategy_session=_one_step_session("Homo sapiens REF")
    )

    drawn = [
        [
            str(r["id"])
            for r in returned(
                await results.get_sample_records(ctx, 441126163, limit=5),
                SampleRecordsResult,
            ).records
        ]
        for ctx in (before, after)
    ]

    assert drawn[0] != drawn[1]
