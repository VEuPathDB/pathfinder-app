from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb.wdk import WDKAttributeHistogram, WDKFilterValue

from strategist.services.experiment import weight_counts
from strategist.services.experiment.weight_counts import count_weights


class _Site:
    def __init__(self, data: dict[str, int]) -> None:
        self.data = data
        self.asked: list[tuple[int, str, list[str] | None]] = []

    async def get_step_histogram(
        self,
        step_id: int,
        column: str,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAttributeHistogram:
        self.asked.append(
            (
                step_id,
                column,
                None if view_filters is None else [f.name for f in view_filters],
            )
        )
        return WDKAttributeHistogram(
            data=self.data,
            type="int",
            attr_label="Search Weight",
            record_count_label="# of Genes",
        )


def _serve(monkeypatch: pytest.MonkeyPatch, data: dict[str, int]) -> _Site:
    site = _Site(data)
    monkeypatch.setattr(weight_counts, "get_strategy_api", lambda _site_id: site)
    return site


async def test_a_transcript_step_is_counted_one_row_per_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, {"1": 2030, "2": 1055, "3": 231})

    counts = await count_weights("plasmodb", 227354670, "transcript")

    assert (counts, site.asked) == (
        {3: 231, 2: 1055, 1: 2030},
        [(227354670, "wdk_weight", ["representativeTranscriptOnly"])],
    )


async def test_a_gene_step_sends_no_view_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, {"5": 84})

    counts = await count_weights("plasmodb", 101, "gene")

    assert (counts, site.asked) == ({5: 84}, [(101, "wdk_weight", None)])
