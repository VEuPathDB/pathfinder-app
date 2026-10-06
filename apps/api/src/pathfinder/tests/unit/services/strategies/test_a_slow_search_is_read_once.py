from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest
from cachetools import LRUCache
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies import measurements, slow_searches, wdk_counts
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.services.strategies.slow_searches import counts_slowly
from pathfinder.services.strategies.wdk_counts import count_bound_criterion
from pathfinder.tests._support.recorded_counts import (
    PERCENTILE_SEARCH,
    recorded_count,
    serve_counts,
)
from pathfinder.tests._support.recorded_searches import suite_search

_PCT = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_PROFILESET = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)


@pytest.fixture(autouse=True)
def no_search_is_slow_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(slow_searches, "_SLOW_SEARCHES", LRUCache(maxsize=8))


def _params(min_value: str) -> dict[str, ParamValue]:
    return {
        "profileset_generic": SinglePickValue(value=_PROFILESET),
        "samples_percentile_generic": MultiPickValue(values=["asexual blood stages"]),
        "min_expression_percentile": StringValue(value=min_value),
        "max_expression_percentile": StringValue(value="100"),
        "any_or_all": SinglePickValue(value="any"),
        "protein_coding_only": SinglePickValue(value="yes"),
        "channel": SinglePickValue(value="Channel 1"),
    }


async def _measure(counts: TurnCounts, min_value: str) -> list[Measurement]:
    params = _params(min_value)
    return await measure_binding(
        counts,
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name=PERCENTILE_SEARCH,
            params=params,
            count=recorded_count("report_percentile_min_80"),
        ),
        values={
            name: BoundValue(
                value=value,
                source="chosen" if name == "min_expression_percentile" else "stated",
            )
            for name, value in params.items()
        },
        infos=format_param_info_typed(list(_PCT.parameters or [])),
    )


async def _slow_count(
    _site_id: str,
    _record_type: str,
    _search_name: str,
    _params: Mapping[str, ParamValue],
    *,
    timeout_seconds: float | None = None,
) -> int | None:
    del timeout_seconds
    await asyncio.sleep(0.02)
    return 12


@pytest.mark.asyncio
async def test_a_search_the_site_counts_slowly_reads_no_other_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, lambda _s, _p: 5318)
    monkeypatch.setattr(slow_searches, "SLOW_COUNT_SECONDS", 0.01)
    monkeypatch.setattr(wdk_counts, "count_search_answer", _slow_count)
    await count_bound_criterion(
        "plasmodb", "transcript", PERCENTILE_SEARCH, _params("80")
    )

    measured = await _measure(TurnCounts(), "80")

    assert asked == []
    assert [(m.kind, m.param) for m in measured] == [
        ("not_measurable", "min_expression_percentile")
    ]


@pytest.mark.asyncio
async def test_a_bind_count_slower_than_the_mark_marks_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slow_searches, "SLOW_COUNT_SECONDS", 0.01)
    monkeypatch.setattr(wdk_counts, "count_search_answer", _slow_count)

    await count_bound_criterion(
        "plasmodb", "transcript", PERCENTILE_SEARCH, _params("80")
    )

    assert counts_slowly("plasmodb", PERCENTILE_SEARCH) is True
    assert counts_slowly("toxodb", PERCENTILE_SEARCH) is False


@pytest.mark.asyncio
async def test_a_reading_slower_than_the_mark_marks_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slow_searches, "SLOW_COUNT_SECONDS", 0.01)
    monkeypatch.setattr(measurements, "count_search_answer", _slow_count)

    await TurnCounts().count(
        "plasmodb", "transcript", PERCENTILE_SEARCH, _params("0"), timeout_seconds=1.0
    )

    assert counts_slowly("plasmodb", PERCENTILE_SEARCH) is True


@pytest.mark.asyncio
async def test_a_fast_count_marks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_counts(monkeypatch, lambda _s, _p: 5318)

    await TurnCounts().count(
        "plasmodb", "transcript", PERCENTILE_SEARCH, _params("0"), timeout_seconds=1.0
    )

    assert counts_slowly("plasmodb", PERCENTILE_SEARCH) is False


@pytest.mark.asyncio
async def test_one_configuration_asked_twice_at_once_is_sent_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    async def _count(
        _site_id: str,
        _record_type: str,
        search_name: str,
        _params: Mapping[str, ParamValue],
        *,
        timeout_seconds: float | None = None,
    ) -> int | None:
        del timeout_seconds
        asked.append(search_name)
        await asyncio.sleep(0.01)
        return 5318

    monkeypatch.setattr(measurements, "count_search_answer", _count)
    counts = TurnCounts()

    both = await asyncio.gather(
        *(
            counts.count(
                "plasmodb",
                "transcript",
                PERCENTILE_SEARCH,
                _params("0"),
                timeout_seconds=1.0,
            )
            for _ in range(2)
        )
    )

    assert both == [5318, 5318]
    assert asked == [PERCENTILE_SEARCH]


@pytest.mark.asyncio
async def test_the_binds_own_configuration_is_not_counted_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, lambda _s, _p: 1)
    counts = TurnCounts()

    await _measure(counts, "80")
    again = await counts.count(
        "plasmodb", "transcript", PERCENTILE_SEARCH, _params("80"), timeout_seconds=1.0
    )

    assert again == recorded_count("report_percentile_min_80")
    assert asked == [PERCENTILE_SEARCH]
