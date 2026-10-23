"""A sample of N reads one gene at each of N offsets spread over the step, in one
report when the step holds at most ten records per sampled gene and otherwise in
one window of each quarter, so a gene family whose ids sort together fills one
offset and not the sample."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic_ai import Tool
from veupathdb.wdk import WDKAnswer, WDKFilterValue, WDKSortSpec
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import _sample_page, results, step_ids
from pathfinder.ai.tools.standalone._result_models import MAX_SAMPLE_LIMIT
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.classed_strategy import classed_strategy
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_GENE_TOTAL = 840
_STEP = 42


class _Step:
    """A transcript step of 840 genes whose record at offset n is gene n."""

    def __init__(self, total: int = _GENE_TOTAL) -> None:
        self.total = total
        self.pages: list[dict[str, int] | None] = []
        self.views: list[list[str]] = []

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
        del step_id, attributes, tables, sorting
        self.pages.append(pagination)
        self.views.append([view.name for view in view_filters or []])
        page = pagination or {}
        offset, wanted = page.get("offset", 0), page.get("numRecords", 0)
        return WDKAnswer.model_validate(
            {
                "meta": {
                    "displayTotalCount": self.total,
                    "attributes": ["gene_product"],
                },
                "records": [
                    {
                        "displayName": f"AGAP{gene:06d}-RA",
                        "id": [
                            {"name": "gene_source_id", "value": f"AGAP{gene:06d}"},
                            {"name": "source_id", "value": f"AGAP{gene:06d}-RA"},
                        ],
                        "attributes": {"gene_product": "<i>cytochrome P450</i>"},
                    }
                    for gene in range(offset, offset + wanted)
                ],
            }
        )


async def test_each_sampled_gene_is_read_from_its_own_window_of_each_quarter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step()
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)
    monkeypatch.setattr(_sample_page, "_drawn", lambda key: -1)

    sampled = await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=8,
        attributes=["gene_product"],
        record_type="transcript",
        seed="m:42",
    )

    assert step.pages == [
        {"offset": 0, "numRecords": 0},
        {"offset": 199, "numRecords": 11},
        {"offset": 409, "numRecords": 11},
        {"offset": 619, "numRecords": 11},
        {"offset": 829, "numRecords": 11},
    ]
    assert set(map(tuple, step.views)) == {("representativeTranscriptOnly",)}
    assert sampled.gene_ids == [
        "AGAP000199",
        "AGAP000209",
        "AGAP000409",
        "AGAP000419",
        "AGAP000619",
        "AGAP000629",
        "AGAP000829",
        "AGAP000839",
    ]
    assert sampled.result.records[0] == {
        "id": "AGAP000199-RA",
        "gene_product": "cytochrome P450",
    }


async def test_a_step_of_ten_records_per_sampled_gene_is_read_in_one_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step()
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)
    monkeypatch.setattr(_sample_page, "_drawn", lambda key: -1)

    sampled = await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=84,
        attributes=None,
        record_type="transcript",
        seed="m:42",
    )

    assert step.pages == [
        {"offset": 0, "numRecords": 0},
        {"offset": 9, "numRecords": 831},
    ]
    assert sampled.gene_ids == [f"AGAP{gene:06d}" for gene in range(9, 840, 10)]


async def test_each_window_of_a_large_step_ends_inside_its_quarter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step(523_795)
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)
    monkeypatch.setattr(_sample_page, "_drawn", lambda key: -1)

    sampled = await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=100,
        attributes=None,
        record_type="transcript",
        seed="m:42",
    )

    assert step.pages == [
        {"offset": 0, "numRecords": 0},
        {"offset": 130_707, "numRecords": 241},
        {"offset": 261_656, "numRecords": 241},
        {"offset": 392_605, "numRecords": 241},
        {"offset": 523_554, "numRecords": 241},
    ]
    assert sampled.gene_ids[24::25] == [
        "AGAP130947",
        "AGAP261896",
        "AGAP392845",
        "AGAP523794",
    ]


async def test_a_large_step_is_sampled_in_one_window_of_each_quarter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step(523_795)
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)

    sampled = await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=100,
        attributes=["gene_product"],
        record_type="transcript",
        seed="m:42",
    )

    [count, *windows] = step.pages
    assert count == {"offset": 0, "numRecords": 0}
    assert len(windows) == _sample_page.SAMPLE_REPORTS == 4
    assert [
        (
            window["numRecords"] <= 25 * _sample_page.SAMPLE_STRIDE,
            quarter * 523_795 // 4 <= window["offset"],
            window["offset"] + window["numRecords"] <= (quarter + 1) * 523_795 // 4,
        )
        for quarter, window in enumerate(w for w in windows if w is not None)
    ] == [(True, True, True)] * 4
    assert len(set(sampled.gene_ids)) == 100
    assert [int(g.removeprefix("AGAP")) * 4 // 523_795 for g in sampled.gene_ids] == [
        quarter for quarter in range(4) for _ in range(25)
    ]


async def test_a_large_step_sampled_at_five_reads_four_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step(523_795)
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)
    monkeypatch.setattr(_sample_page, "_drawn", lambda key: -1)

    sampled = await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=5,
        attributes=None,
        record_type="transcript",
        seed="m:42",
    )

    assert [page["numRecords"] for page in step.pages if page is not None] == [
        0,
        1,
        1,
        1,
        11,
    ]
    assert len(set(sampled.gene_ids)) == 5


@pytest.mark.parametrize(
    ("total", "limit", "reports", "read"),
    [(20_001, 2000, 4, 2000), (1001, 5000, 1, 1001)],
)
async def test_any_limit_samples_inside_the_step(
    monkeypatch: pytest.MonkeyPatch, total: int, limit: int, reports: int, read: int
) -> None:
    step = _Step(total)
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)

    sampled = await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=limit,
        attributes=None,
        record_type="transcript",
        seed="m:42",
    )

    assert len(step.pages) == 1 + reports
    assert len(set(sampled.gene_ids)) == read
    assert max(int(g.removeprefix("AGAP")) for g in sampled.gene_ids) < total


def test_the_offsets_fall_one_in_each_stride() -> None:
    offsets = _sample_page.spread_offsets(_GENE_TOTAL, 8, seed="m:42")

    assert [o // 105 for o in offsets] == list(range(8))


def test_a_step_smaller_than_the_sample_is_read_whole() -> None:
    assert _sample_page.spread_offsets(3, 8, seed="m:42") == [0, 1, 2]


def test_a_hundred_records_sampled_at_eight_give_eight_offsets_across_the_step() -> (
    None
):
    offsets = _sample_page.spread_offsets(100, 8, seed="m:42")

    assert len(set(offsets)) == 8
    assert [i * 100 // 8 <= o < (i + 1) * 100 // 8 for i, o in enumerate(offsets)] == [
        True
    ] * 8


def test_an_empty_step_has_no_offset() -> None:
    assert _sample_page.spread_offsets(0, 8, seed="m:42") == []


def _built_step() -> StrategySession:
    return classed_strategy("vectorbase", {"step_p450": _STEP})


async def test_the_id_read_and_the_sample_answer_the_same_genes_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step()
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)

    async def no_selected(
        site_id: str, record_type: str, graph: object, *, own_search: str | None
    ) -> list[str]:
        del site_id, record_type, graph, own_search
        return []

    monkeypatch.setattr(results, "sample_attributes", no_selected)
    session = _built_step()

    ids = returned(
        await step_ids.read_step_ids(
            agent_run_context(site_id="vectorbase", strategy_session=session),
            _STEP,
            limit=8,
        ),
        step_ids.StepGeneIds,
    )
    sample = returned(
        await results.get_sample_records(
            agent_run_context(site_id="vectorbase", strategy_session=session),
            _STEP,
            limit=8,
        ),
        SampleRecordsResult,
    )

    assert (ids.total, ids.complete) == (_GENE_TOTAL, False)
    assert ids.gene_ids == [str(r["id"]).removesuffix("-RA") for r in sample.records]


def test_a_limited_id_read_takes_no_more_ids_than_a_sample() -> None:
    """A limited read takes its ids from one report, as the sample does."""
    schema = Tool(step_ids.read_step_ids).tool_def.parameters_json_schema

    [limited, _] = schema["properties"]["limit"]["anyOf"]

    assert (limited["minimum"], limited["maximum"]) == (1, MAX_SAMPLE_LIMIT)
