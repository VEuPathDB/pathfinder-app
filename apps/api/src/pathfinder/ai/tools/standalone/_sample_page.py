import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from pydantic import Field
from veupathdb import JSONObject, strip_html_tags
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    StrategyAPI,
    WDKAnswer,
    WDKFilterValue,
    WDKRecordInstance,
    get_strategy_api,
)
from veupathdb_mcp.wdk import SampleRecordsResult, view_filters_for

from pathfinder.services.gene_sets.step_genes import extract_gene_id

SAMPLE_REPORTS = 4
SAMPLE_STRIDE = 10
_REFUSAL_STATUSES = range(400, 500)


class StepSample(SampleRecordsResult):
    dropped_attributes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class SampledRecords:
    """One page of a step's records, and the gene each row names."""

    result: StepSample
    gene_ids: list[str]


def _row(record: WDKRecordInstance, attributes: list[str]) -> JSONObject:
    texts: JSONObject = {
        name: None
        if (text := record.attribute_text(name)) is None
        else strip_html_tags(text)
        for name in attributes
    }
    return {"id": record.display_name, **texts}


def spread_offsets(total: int, limit: int, *, seed: str) -> list[int]:
    """One offset in each of ``limit`` equal strides of the step, placed within
    its stride by the seed, so one seed always reads the same records."""
    count = min(limit, total)
    if count == 0:
        return []
    starts = [i * total // count for i in range(count + 1)]
    return [
        start + _drawn(f"{seed}:{index}") % (end - start)
        for index, (start, end) in enumerate(pairwise(starts))
    ]


def _sample_windows(total: int, limit: int, *, seed: str) -> list[list[int]]:
    count = min(limit, total)
    if total <= count * SAMPLE_STRIDE:
        offsets = spread_offsets(total, count, seed=seed)
        return [offsets] if offsets else []
    reports = min(SAMPLE_REPORTS, count)
    windows: list[list[int]] = []
    for index in range(reports):
        size = count * (index + 1) // reports - count * index // reports
        low, high = index * total // reports, (index + 1) * total // reports
        length = min(high - low, size * SAMPLE_STRIDE)
        start = low + _drawn(f"{seed}:window:{index}") % (high - low - length + 1)
        inside = spread_offsets(length, size, seed=f"{seed}:{index}")
        windows.append([start + offset for offset in inside])
    return windows


def _drawn(key: str) -> int:
    return int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest())


def _refused(error: VEuPathDBError[StrEnum], asked: list[str]) -> list[str]:
    if not _REFUSAL_STATUSES.start <= error.status < _REFUSAL_STATUSES.stop:
        return []
    said = str(error)
    return [name for name in asked if f"Attribute '{name}'" in said]


async def _read_windows(
    api: StrategyAPI,
    step_id: int,
    windows: list[list[int]],
    *,
    attributes: list[str] | None,
    view: Sequence[WDKFilterValue] | None,
) -> tuple[list[WDKAnswer], list[str]]:
    asked = attributes or None
    dropped: list[str] = []
    answers: list[WDKAnswer] = []
    for window in windows:
        page = {"offset": window[0], "numRecords": window[-1] - window[0] + 1}
        answer: WDKAnswer | None = None
        while answer is None:
            try:
                answer = await api.get_step_records(
                    step_id, attributes=asked, pagination=page, view_filters=view
                )
            except VEuPathDBError as error:
                named = _refused(error, asked or [])
                if not named:
                    raise
                kept = [] if dropped else [n for n in asked or [] if n not in named]
                dropped += [name for name in asked or [] if name not in kept]
                asked = kept or None
        answers.append(answer)
    return answers, dropped


async def sample_page(
    site_id: str,
    step_id: int,
    *,
    limit: int,
    attributes: list[str] | None,
    record_type: str,
    seed: str,
) -> SampledRecords:
    api = get_strategy_api(site_id)
    view = view_filters_for(record_type)
    counted = await api.get_step_records(
        step_id, pagination={"offset": 0, "numRecords": 0}, view_filters=view
    )
    total = counted.meta.records_returned()
    windows = _sample_windows(total, limit, seed=seed)
    answers, dropped = await _read_windows(
        api, step_id, windows, attributes=attributes, view=view
    )
    records = [
        answer.records[i]
        for window, answer in zip(windows, answers, strict=True)
        for offset in window
        if (i := offset - window[0]) < len(answer.records)
    ]
    shown = [
        name
        for name in (answers[0].meta.attributes if answers else [])
        if all(name in answer.meta.attributes for answer in answers)
    ]
    return SampledRecords(
        result=StepSample(
            step_id=step_id,
            total_count=total,
            records=[_row(record, shown) for record in records],
            attributes=shown,
            dropped_attributes=dropped,
        ),
        gene_ids=[gene_id for r in records if (gene_id := extract_gene_id(r))],
    )
