"""The rows of a column tally: each value with the records that hold it, most first."""

from __future__ import annotations

from collections.abc import Iterable

from assistant_core.platform.pydantic_base import CamelModel
from veupathdb import strip_html_tags
from veupathdb.domain import WDKHistogramBin
from veupathdb.wdk.wdk_models import WDKColumnDistribution

KEPT_ROWS = 200


class TallyRow(CamelModel):
    value: str
    count: int
    label: str = ""


def sorted_rows(rows: Iterable[TallyRow]) -> list[TallyRow]:
    return sorted(rows, key=lambda row: (-row.count, row.value))


def shown_text(value: str) -> str:
    return strip_html_tags(value).strip()


def shown_value(bin_: WDKHistogramBin) -> str:
    return shown_text(bin_.bin_label or bin_.bin_start)


def counted_rows(counts: Iterable[tuple[str, int]]) -> list[TallyRow]:
    shown = ((shown_text(value), count) for value, count in counts)
    return sorted_rows(TallyRow(value=v, count=n) for v, n in shown if v)


def distribution_rows(distribution: WDKColumnDistribution) -> list[TallyRow]:
    return counted_rows(
        (b.bin_label or b.bin_start, b.value) for b in distribution.histogram
    )
