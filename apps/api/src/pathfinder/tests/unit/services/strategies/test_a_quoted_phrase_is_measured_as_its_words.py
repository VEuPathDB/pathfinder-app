"""A chosen quoted text matches each quoted operand as one phrase, so it is
counted again with the quotes around each phrase removed."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.tests._support.recorded_counts import (
    GIARDIA_WB,
    recorded_site_search,
    serve_counts,
    serve_site_search,
    wire,
)
from pathfinder.tests._support.recorded_searches import suite_search

_SHEET = format_param_info_typed(
    suite_search("search_giardiadb_genes_by_text").parameters or []
)
# GiardiaDB GenesByText over product and Products in Giardia Assemblage A
# isolate WB, read live: each operand as a phrase, and the unquoted words.
_PHRASES, _WORDS = 261, 7131
_QUOTED = '"variant-specific surface protein" OR VSP'
_UNQUOTED = "variant-specific surface protein OR VSP"


def _count(_search: str, params: Mapping[str, ParamValue]) -> int | None:
    return {_QUOTED: _PHRASES, _UNQUOTED: _WORDS}.get(wire(params, "text_expression"))


async def _measure() -> list[Measurement]:
    params: dict[str, ParamValue] = {
        "text_expression": StringValue(value=_QUOTED),
        "text_search_organism": MultiPickValue(values=[GIARDIA_WB]),
        "text_fields": MultiPickValue(values=["product", "Products"]),
    }
    return await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="giardiadb",
            record_type="transcript",
            search_name="GenesByText",
            params=params,
            count=_PHRASES,
            organism_param="text_search_organism",
        ),
        values={
            name: BoundValue(
                value=value,
                source="chosen" if name == "text_expression" else "stated",
            )
            for name, value in params.items()
        },
        infos=_SHEET,
    )


@pytest.mark.asyncio
async def test_a_chosen_quoted_phrase_is_counted_as_its_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _count)
    serve_site_search(monkeypatch, recorded_site_search("site_search_vsp"))

    measured = await _measure()

    assert [m.kind for m in measured] == ["site_search_reach", "words_reading"]
    assert measured[1] == Measurement(
        kind="words_reading", param="text_expression", count=_WORDS, reading=_UNQUOTED
    )


@pytest.mark.asyncio
async def test_a_words_count_that_did_not_arrive_is_recorded_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, lambda _search, _params: None)
    serve_site_search(monkeypatch, recorded_site_search("site_search_vsp"))

    measured = await _measure()

    assert measured[1:] == [
        Measurement(kind="words_reading", param="text_expression", reading=_UNQUOTED)
    ]
