from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from veupathdb import strip_html_tags
from veupathdb.wdk import get_strategy_api

PAGED_RECORDS = 2_000
GENOME_COLUMN = "organism_full"


@dataclass(frozen=True)
class PagedCounts:
    total: int
    counts: Counter[str]


async def count_paged_values(
    site_id: str, wdk_step_id: int, column: str
) -> PagedCounts:
    answer = await get_strategy_api(site_id).get_step_answer(
        wdk_step_id,
        attributes=[column],
        pagination={"offset": 0, "numRecords": PAGED_RECORDS},
    )
    held = (strip_html_tags(record.attribute_text(column)) for record in answer.records)
    return PagedCounts(
        total=answer.meta.records_returned(),
        counts=Counter(value for value in held if value),
    )
