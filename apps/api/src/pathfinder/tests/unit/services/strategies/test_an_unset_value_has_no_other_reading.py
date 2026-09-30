"""A value that states nothing has no other reading: a site placeholder and
the radio-off value are measured neither by the site search nor by count."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.tests._support.recorded_counts import (
    recorded_site_search,
    serve_counts,
    serve_site_search,
)
from pathfinder.tests._support.recorded_searches import client_search, suite_search


def _sheet(search: WDKSearch) -> list[ParameterInfo]:
    return format_param_info_typed(list(search.parameters or []))


def _defaults(params: Mapping[str, ParamValue]) -> dict[str, BoundValue]:
    return {
        name: BoundValue(value=value, source="default")
        for name, value in params.items()
    }


def _no_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    msg = f"an unset value is counted: {dict(params)}"
    raise AssertionError(msg)


async def _measure_unset(
    fixture: str, search_name: str, params: dict[str, ParamValue], count: int
) -> list[Measurement]:
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name=search_name,
            params=params,
            count=count,
        ),
        values=_defaults(params),
        infos=[
            info
            for info in _sheet(
                client_search(fixture)
                if fixture == "search_genes_by_location"
                else suite_search(fixture)
            )
            if info.name in params
        ],
    )


@pytest.mark.asyncio
async def test_a_site_placeholder_has_no_other_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _no_count)
    site_search = serve_site_search(
        monkeypatch, recorded_site_search("site_search_vsp")
    )

    measured = await _measure_unset(
        "search_genes_by_location",
        "GenesByLocation",
        {"sequenceId": StringValue(value="(Example: Pf3D7_04_v3)")},
        2268,
    )

    assert (measured, asked, site_search.asked) == ([], [], [])


@pytest.mark.asyncio
async def test_the_radio_off_value_has_no_other_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _no_count)

    measured = await _measure_unset(
        "search_genes_by_interpro_domain",
        "GenesByInterproDomain",
        {"domain_accession": StringValue(value="N/A")},
        144,
    )

    assert (measured, asked) == ([], [])


@pytest.mark.asyncio
async def test_an_unset_value_of_a_binding_that_counted_nothing_is_not_listed() -> None:
    params: dict[str, ParamValue] = {"domain_accession": StringValue(value="N/A")}

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByInterproDomain",
            params=params,
            count=None,
        ),
        values=_defaults(params),
        infos=_sheet(suite_search("search_genes_by_interpro_domain")),
    )

    assert measured == []
