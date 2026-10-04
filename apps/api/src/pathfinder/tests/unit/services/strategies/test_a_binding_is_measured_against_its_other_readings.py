"""The counts the site returns for other readings of a bound value, from the
recorded reports: the loosest bound, the wildcard form, the site search, and a
species group read both ways."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.wdk import (
    SiteSearchResponse,
    WDKSearch,
    phyletic_tree_of,
)
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Measurement,
    ValueSource,
)
from pathfinder.services.strategies import measurements
from pathfinder.services.strategies.measurements import (
    MEASUREMENT_BUDGET_SECONDS,
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.services.strategies.wdk_counts import COUNT_BUDGET_SECONDS
from pathfinder.tests._support.recorded_counts import (
    CRYPTO_IOWA,
    GIARDIA_WB,
    PERCENTILE_SEARCH,
    TGON_STRAINS,
    recorded_count,
    recorded_site_search,
    serve_counts,
    serve_site_search,
    wire,
)
from pathfinder.tests._support.recorded_searches import suite_search

_PCT = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_TEXT = suite_search("search_genes_by_text")
_ORTHOLOG = suite_search("search_genes_by_ortholog_pattern")
_BUDGET = 1.0
_PROFILESET = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)


def _sheet(search: WDKSearch) -> list[ParameterInfo]:
    return format_param_info_typed(list(search.parameters or []))


def _percentile_params(min_value: str) -> dict[str, ParamValue]:
    return {
        "profileset_generic": SinglePickValue(value=_PROFILESET),
        "samples_percentile_generic": MultiPickValue(values=["asexual blood stages"]),
        "min_expression_percentile": StringValue(value=min_value),
        "max_expression_percentile": StringValue(value="100"),
        "any_or_all": SinglePickValue(value="any"),
        "protein_coding_only": SinglePickValue(value="yes"),
        "channel": SinglePickValue(value="Channel 1"),
    }


def _bound(
    params: Mapping[str, ParamValue], sources: Mapping[str, ValueSource]
) -> dict[str, BoundValue]:
    return {
        name: BoundValue(value=value, source=sources.get(name, "stated"))
        for name, value in params.items()
    }


def _percentile_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    if wire(params, "max_expression_percentile") == "0":
        return 0
    if wire(params, "min_expression_percentile") == "0":
        return recorded_count("report_percentile_min_0")
    return recorded_count("report_percentile_min_80")


async def _measure_percentile(source: ValueSource) -> list[Measurement]:
    params = _percentile_params("80")
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name=PERCENTILE_SEARCH,
            params=params,
            count=recorded_count("report_percentile_min_80"),
        ),
        values=_bound(params, {"min_expression_percentile": source}),
        infos=_sheet(_PCT),
    )


@pytest.mark.asyncio
async def test_a_default_threshold_is_counted_at_its_loosest_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _percentile_count)

    measured = await _measure_percentile("default")

    assert recorded_count("report_percentile_min_80") == 1087
    assert measured == [
        Measurement(
            kind="loosest_bound",
            param="min_expression_percentile",
            count=5318,
            reading="0",
        )
    ]


@pytest.mark.asyncio
async def test_a_stated_threshold_is_not_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _percentile_count)

    assert await _measure_percentile("stated") == []
    assert asked == []


@pytest.mark.asyncio
async def test_a_reading_the_site_does_not_count_is_recorded_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, lambda _s, _p: None)

    assert await _measure_percentile("default") == [
        Measurement(
            kind="loosest_bound", param="min_expression_percentile", reading="0"
        )
    ]


@pytest.mark.asyncio
async def test_a_bound_reading_that_counts_fewer_is_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, lambda _s, _p: 12)

    assert await _measure_percentile("default") == []


@pytest.mark.asyncio
async def test_every_read_has_the_measurement_budget_and_not_the_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budgets: list[float | None] = []
    serve_counts(monkeypatch, _percentile_count, budgets)

    await _measure_percentile("chosen")

    assert len(budgets) == 1
    assert all(
        b is not None and COUNT_BUDGET_SECONDS < b <= MEASUREMENT_BUDGET_SECONDS
        for b in budgets
    )


def _text_params(expression: str) -> dict[str, ParamValue]:
    return {
        "text_expression": StringValue(value=expression),
        "text_search_organism": MultiPickValue(values=[GIARDIA_WB]),
        "document_type": StringValue(value="gene"),
        "text_fields": MultiPickValue(values=["product"]),
    }


async def _measure_text(expression: str, count: int) -> list[Measurement]:
    params = _text_params(expression)
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="giardiadb",
            record_type="transcript",
            search_name="GenesByText",
            params=params,
            count=count,
            organism_param="text_search_organism",
        ),
        values=_bound(params, {"text_expression": "chosen"}),
        infos=_sheet(_TEXT),
    )


def _text_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    if wire(params, "text_expression") == "VSP*":
        return recorded_count("report_text_vsp_wildcard")
    return recorded_count("report_text_vsp_quoted")


@pytest.mark.asyncio
async def test_a_chosen_quoted_word_is_counted_as_a_wildcard_and_in_site_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _text_count)
    site_search = serve_site_search(
        monkeypatch, recorded_site_search("site_search_vsp")
    )

    measured = await _measure_text('"VSP"', recorded_count("report_text_vsp_quoted"))

    assert recorded_count("report_text_vsp_quoted") == 196
    assert measured == [
        Measurement(
            kind="site_search_reach",
            param="text_expression",
            count=333,
            reading='"VSP"',
        ),
        Measurement(
            kind="wildcard_phrase", param="text_expression", count=207, reading="VSP*"
        ),
    ]
    assert site_search.asked == [('"VSP"', [GIARDIA_WB])]


@pytest.mark.asyncio
async def test_a_wildcard_count_that_did_not_arrive_is_recorded_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, lambda _s, _p: None)
    serve_site_search(monkeypatch, recorded_site_search("site_search_vsp"))

    measured = await _measure_text('"VSP"', recorded_count("report_text_vsp_quoted"))

    assert measured[1:] == [
        Measurement(kind="wildcard_phrase", param="text_expression", reading="VSP*")
    ]


@dataclass
class _SlowSiteSearch:
    async def search(
        self, _text: str, *, organisms: list[str] | None = None, limit: int = 20
    ) -> SiteSearchResponse:
        del organisms, limit
        await asyncio.sleep(1)
        return recorded_site_search("site_search_vsp")

    def get_site_search_client(self, _site_id: str) -> _SlowSiteSearch:
        return self


@pytest.mark.asyncio
async def test_a_site_search_past_the_budget_is_recorded_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _text_count)
    monkeypatch.setattr(measurements, "MEASUREMENT_BUDGET_SECONDS", 0.01)
    monkeypatch.setattr(measurements, "get_site_router", _SlowSiteSearch)

    assert await _measure_text('"VSP"', 196) == [
        Measurement(kind="site_search_reach", param="text_expression", reading='"VSP"')
    ]
    assert asked == []


@pytest.mark.asyncio
async def test_a_quoted_phrase_of_several_words_has_no_wildcard_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The search reads no wildcard inside quotes, so a phrase has no wildcard form."""
    asked = serve_counts(monkeypatch, _text_count)
    site_search = serve_site_search(
        monkeypatch, recorded_site_search("site_search_vsp")
    )

    measured = await _measure_text('"surface protein"', 21)

    assert [(m.kind, m.reading) for m in measured] == [
        ("site_search_reach", '"surface protein"'),
        ("words_reading", "surface protein"),
    ]
    assert (asked, site_search.asked) == (
        ["GenesByText"],
        [('"surface protein"', [GIARDIA_WB])],
    )


@pytest.mark.asyncio
async def test_an_unquoted_word_is_recorded_as_not_measurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _text_count)
    site_search = serve_site_search(
        monkeypatch, recorded_site_search("site_search_vsp")
    )

    assert await _measure_text("VSP", 196) == [
        Measurement(
            kind="not_measurable",
            param="text_expression",
            reading="an unquoted single word is counted as written",
        )
    ]
    assert (asked, site_search.asked) == ([], [])


@pytest.mark.asyncio
async def test_a_search_the_site_search_does_not_bridge_is_not_measurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _text_count)
    other = SiteSearchResponse.model_validate(
        {
            "documentTypes": [
                {
                    "id": "compound",
                    "displayName": "Compound",
                    "displayNamePlural": "Compounds",
                    "count": 7,
                    "wdkSearchName": "CompoundsByText",
                }
            ]
        }
    )
    serve_site_search(monkeypatch, other)

    assert await _measure_text('"VSP"', 196) == [
        Measurement(
            kind="not_measurable",
            param="text_expression",
            reading="the site search does not read this search",
        )
    ]
    assert asked == []


def _ortholog_params(states: str) -> dict[str, ParamValue]:
    return {
        "organism": MultiPickValue(values=[CRYPTO_IOWA]),
        "phyletic_indent_map": MultiPickValue(values=[]),
        "phyletic_term_map": MultiPickValue(values=[]),
        "included_species": StringValue(value=", ".join(TGON_STRAINS)),
        "excluded_species": StringValue(value="hsap"),
        "profile_pattern": StringValue(value=states),
    }


def _pattern(states: str) -> str:
    return "%" + "%".join(["hsap:N", *(f"{c}:{states}" for c in TGON_STRAINS)]) + "%"


def _ortholog_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    """The recorded count of each pattern the recorded reports sent, and no other."""
    return {
        "%hsap:N%": recorded_count("report_ortholog_tgon_omitted"),
        _pattern("N"): recorded_count("report_ortholog_tgon_none"),
        _pattern("Y"): recorded_count("report_ortholog_tgon_all"),
    }[wire(params, "profile_pattern")]


async def _measure_strains() -> list[Measurement]:
    params = _ortholog_params(_pattern("Y"))
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="cryptodb",
            record_type="transcript",
            search_name="GenesByOrthologPattern",
            params=params,
            count=recorded_count("report_ortholog_tgon_all"),
        ),
        values=_bound(params, {"included_species": "chosen"}),
        infos=_sheet(_ORTHOLOG),
        tree=phyletic_tree_of(list(_ORTHOLOG.parameters or [])),
    )


@pytest.mark.asyncio
async def test_a_chosen_species_group_is_counted_both_ways(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _ortholog_count)

    measured = await _measure_strains()

    assert (
        recorded_count("report_ortholog_tgon_omitted"),
        recorded_count("report_ortholog_tgon_none"),
    ) == (1832, 1335)
    assert measured == [
        Measurement(
            kind="any_strain",
            param="included_species",
            count=497,
            reading="at least one of 15 species",
        ),
        Measurement(
            kind="all_strains",
            param="included_species",
            count=484,
            reading="all 15 species",
        ),
    ]


@pytest.mark.asyncio
async def test_a_strain_count_that_did_not_arrive_is_recorded_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_omitted(search: str, params: Mapping[str, ParamValue]) -> int | None:
        if wire(params, "profile_pattern") == "%hsap:N%":
            return None
        return _ortholog_count(search, params)

    serve_counts(monkeypatch, _no_omitted)

    measured = await _measure_strains()

    assert [(m.kind, m.count) for m in measured] == [
        ("any_strain", None),
        ("all_strains", 484),
    ]


@pytest.mark.asyncio
async def test_a_turn_counts_one_configuration_once_per_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, _percentile_count)
    counts = TurnCounts()
    params = _percentile_params("0")

    first = await counts.count(
        "plasmodb", "transcript", PERCENTILE_SEARCH, params, timeout_seconds=_BUDGET
    )
    again = await counts.count(
        "plasmodb",
        "transcript",
        PERCENTILE_SEARCH,
        dict(reversed(params.items())),
        timeout_seconds=_BUDGET,
    )
    elsewhere = await counts.count(
        "toxodb", "transcript", PERCENTILE_SEARCH, params, timeout_seconds=_BUDGET
    )

    assert (first, again, elsewhere) == (5318, 5318, 5318)
    assert asked == [PERCENTILE_SEARCH, PERCENTILE_SEARCH]


@pytest.mark.asyncio
async def test_a_count_that_did_not_arrive_is_read_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, lambda _s, _p: None)
    counts = TurnCounts()
    params = _percentile_params("0")

    await counts.count(
        "plasmodb", "transcript", PERCENTILE_SEARCH, params, timeout_seconds=_BUDGET
    )
    await counts.count(
        "plasmodb", "transcript", PERCENTILE_SEARCH, params, timeout_seconds=_BUDGET
    )

    assert asked == [PERCENTILE_SEARCH, PERCENTILE_SEARCH]
