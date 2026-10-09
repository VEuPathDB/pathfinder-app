from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from veupathdb.domain.parameters import NumberValue, ParamValue
from veupathdb.wdk import get_site, search_turn
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies import measurements
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)

_BUDGET = 0.3
_AT_THE_SITE = 0.2
_BOUND = 50


def _number(name: str) -> ParameterInfo:
    return ParameterInfo(
        name=name,
        display_name=name,
        type="number",
        required=True,
        is_visible=True,
        help="",
        value_format="",
        min=0,
        max=100,
    )


async def _report(request: httpx.Request) -> httpx.Response:
    await asyncio.sleep(_AT_THE_SITE)
    sent = json.loads(request.content)["searchConfig"]["parameters"]
    count = _BOUND + sum(int(float(value)) for value in sent.values())
    return httpx.Response(200, json={"meta": {"totalCount": count}, "records": []})


@pytest.fixture
def a_slow_site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(measurements, "MEASUREMENT_BUDGET_SECONDS", _BUDGET)
    service_url = get_site("plasmodb").service_url
    with respx.mock(assert_all_mocked=True) as router:
        router.post(url__startswith=service_url).mock(side_effect=_report)
        yield


async def _measure() -> list[Measurement]:
    params: dict[str, ParamValue] = {
        "min_score": NumberValue(value=10),
        "min_length": NumberValue(value=20),
    }
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesBySyntheticScore",
            params=params,
            count=_BOUND,
        ),
        values={
            name: BoundValue(value=value, source="chosen")
            for name, value in params.items()
        },
        infos=[_number("min_score"), _number("min_length")],
    )


@pytest.mark.usefixtures("a_slow_site")
async def test_a_bind_whose_readings_wait_in_its_turn_measures_what_it_would_alone() -> (
    None
):
    alone = await _measure()
    with search_turn():
        in_line = await _measure()

    assert [(m.kind, m.param, m.count, m.reading) for m in alone] == [
        ("loosest_bound", "min_score", 170, "100"),
        ("loosest_bound", "min_length", 160, "100"),
    ]
    assert in_line == alone
