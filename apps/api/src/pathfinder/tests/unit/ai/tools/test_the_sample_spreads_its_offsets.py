"""A sample of N reads one gene at each of N offsets spread over the step, so a
gene family whose ids sort together fills one offset and not the sample."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb.wdk import WDKAnswer, WDKFilterValue, WDKSortSpec

from pathfinder.ai.tools.standalone import results

_GENE_TOTAL = 840


class _Step:
    """A transcript step of 840 genes whose record at offset n is gene n."""

    def __init__(self) -> None:
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
                    "displayTotalCount": _GENE_TOTAL,
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


async def test_each_sampled_gene_is_read_from_its_own_stride_of_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _Step()
    monkeypatch.setattr(results, "get_strategy_api", lambda site_id: step)
    monkeypatch.setattr(results, "_drawn", lambda key: -1)

    sampled = await results.sample_page(
        "vectorbase",
        42,
        limit=8,
        attributes=["gene_product"],
        record_type="transcript",
        seed="m:42",
    )

    assert step.pages == [
        {"offset": 0, "numRecords": 0},
        *(
            {"offset": o, "numRecords": 1}
            for o in (104, 209, 314, 419, 524, 629, 734, 839)
        ),
    ]
    assert set(map(tuple, step.views)) == {("representativeTranscriptOnly",)}
    assert sampled.gene_ids == [
        "AGAP000104",
        "AGAP000209",
        "AGAP000314",
        "AGAP000419",
        "AGAP000524",
        "AGAP000629",
        "AGAP000734",
        "AGAP000839",
    ]
    assert sampled.result.records[0] == {
        "id": "AGAP000104-RA",
        "gene_product": "cytochrome P450",
    }


def test_the_offsets_fall_one_in_each_stride() -> None:
    offsets = results.spread_offsets(_GENE_TOTAL, 8, seed="m:42")

    assert [o // 105 for o in offsets] == list(range(8))


def test_a_step_smaller_than_the_sample_is_read_whole() -> None:
    assert results.spread_offsets(3, 8, seed="m:42") == [0, 1, 2]


def test_a_hundred_records_sampled_at_eight_give_eight_offsets_across_the_step() -> (
    None
):
    offsets = results.spread_offsets(100, 8, seed="m:42")

    assert len(set(offsets)) == 8
    assert [i * 100 // 8 <= o < (i + 1) * 100 // 8 for i, o in enumerate(offsets)] == [
        True
    ] * 8


def test_an_empty_step_has_no_offset() -> None:
    assert results.spread_offsets(0, 8, seed="m:42") == []
