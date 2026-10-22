from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb.wdk import WDKAnswer, WDKFilterValue, WDKSortSpec

from pathfinder.ai.tools.standalone import _sample_page, results
from pathfinder.ai.tools.standalone.step_ids import StepGeneIds, read_step_ids
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_GROUP_STEP = 227284520


class _Groups:
    def __init__(self, total: int) -> None:
        self.total = total
        self.sent = total
        self.pages: list[dict[str, int] | None] = []

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
        self.pages.append(pagination)
        page = pagination or {}
        offset, wanted = page.get("offset", 0), page.get("numRecords", 0)
        return WDKAnswer.model_validate(
            {
                "meta": {"displayViewTotalCount": self.total, "attributes": []},
                "records": [
                    {
                        "displayName": f"OG8_{group:07d}",
                        "id": [{"name": "group_name", "value": f"OG8_{group:07d}"}],
                    }
                    for group in range(offset, min(offset + wanted, self.sent))
                ],
            }
        )


def _serve(monkeypatch: pytest.MonkeyPatch, total: int) -> _Groups:
    step = _Groups(total)
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)
    return step


def _group_step() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph(graph_id="g1", name="every species", site_id="orthomcl")
    graph.record_type = "group"
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"step_root": _GROUP_STEP})
    return session


async def test_a_step_of_a_hundred_records_sampled_at_a_hundred_is_one_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, 100)

    sampled = await _sample_page.sample_page(
        "orthomcl",
        _GROUP_STEP,
        limit=100,
        attributes=None,
        record_type="group",
        seed="s",
    )

    assert step.pages == [
        {"offset": 0, "numRecords": 0},
        {"offset": 0, "numRecords": 100},
    ]
    assert sampled.gene_ids == [f"OG8_{group:07d}" for group in range(100)]


async def test_an_id_read_of_a_hundred_groups_sends_one_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, 787)
    session = _group_step()
    seed = results.step_sample_seed(session, _GROUP_STEP)
    offsets = _sample_page.spread_offsets(787, 100, seed=seed)

    read = returned(
        await read_step_ids(
            agent_run_context(site_id="orthomcl", strategy_session=session),
            _GROUP_STEP,
            limit=100,
        ),
        StepGeneIds,
    )

    assert step.pages == [
        {"offset": 0, "numRecords": 0},
        {"offset": offsets[0], "numRecords": offsets[-1] - offsets[0] + 1},
    ]
    assert read.gene_ids == [f"OG8_{offset:07d}" for offset in offsets]
    assert (len(read.gene_ids), read.total, read.complete) == (100, 787, False)


async def test_an_empty_step_is_counted_and_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, 0)

    sampled = await _sample_page.sample_page(
        "orthomcl",
        _GROUP_STEP,
        limit=100,
        attributes=None,
        record_type="group",
        seed="s",
    )

    assert step.pages == [{"offset": 0, "numRecords": 0}]
    assert (sampled.gene_ids, sampled.result.records) == ([], [])


async def test_a_window_the_site_answers_short_keeps_the_records_it_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, 787)
    step.sent = 400
    offsets = _sample_page.spread_offsets(787, 100, seed="s")

    sampled = await _sample_page.sample_page(
        "orthomcl",
        _GROUP_STEP,
        limit=100,
        attributes=None,
        record_type="group",
        seed="s",
    )

    assert sampled.gene_ids == [
        f"OG8_{offset:07d}" for offset in offsets if offset < 400
    ]
