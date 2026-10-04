"""A text that leaves out the words a requirement phrase writes before it is
chosen, not stated, and the phrase it was cut from is never a reading."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.wdk import SiteSearchResponse
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.tools.standalone._frame_sources import bound_values
from pathfinder.domain.strategy.value_source import cut_from
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.tests._support.recorded_counts import (
    serve_counts,
    serve_site_search,
    wire,
)
from pathfinder.tests._support.recorded_searches import suite_search

_MESSAGE = (
    "Babesia bovis T2Bo genes with a variant erythrocyte surface antigen annotation."
)
_REQUIREMENTS = ["Babesia bovis T2Bo", "variant erythrocyte surface antigen annotation"]
_SHEET = format_param_info_typed(
    suite_search("search_giardiadb_genes_by_text").parameters or []
)
_CYSTEINE = (
    "Giardia muris Roberts-Thompson genes with a cysteine-rich protein annotation."
)


def _source(text: str, message: str, requirements: list[str]) -> str:
    bound = bound_values(
        {"text_expression": StringValue(value=text)},
        infos=_SHEET,
        site_supplied=set(),
        request_texts=[message],
        reason="the model's reason",
        requirement_phrases=requirements,
    )
    return bound["text_expression"].source


def test_a_text_cut_from_a_stated_phrase_is_chosen() -> None:
    assert (
        _source("erythrocyte surface antigen", _MESSAGE, _REQUIREMENTS),
        cut_from(StringValue(value="erythrocyte surface antigen"), _REQUIREMENTS),
    ) == ("chosen", "variant erythrocyte surface antigen")


def test_the_whole_stated_phrase_stays_stated() -> None:
    assert (
        _source("variant erythrocyte surface antigen", _MESSAGE, _REQUIREMENTS),
        cut_from(
            StringValue(value='"variant erythrocyte surface antigen"'), _REQUIREMENTS
        ),
    ) == ("stated", "")


def test_a_word_after_the_text_names_what_it_is_and_cuts_nothing() -> None:
    requirements = [
        "Giardia muris Roberts-Thompson",
        "cysteine-rich protein annotation",
    ]

    assert _source("cysteine-rich protein", _CYSTEINE, requirements) == "stated"


def test_an_article_before_the_text_cuts_nothing() -> None:
    requirements = ["a cysteine-rich protein annotation"]

    assert cut_from(StringValue(value="cysteine-rich protein"), requirements) == ""


def test_only_a_text_is_cut() -> None:
    assert cut_from(MultiPickValue(values=["erythrocyte"]), _REQUIREMENTS) == ""


# PiroplasmaDB GenesByText over product, Products and Notes in B. bovis T2Bo,
# read live: the bound text counts 153 genes.
_BOUND = 153


@pytest.mark.asyncio
async def test_the_phrase_a_text_was_cut_from_is_never_a_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counted: list[str] = []

    def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
        counted.append(wire(params, "text_expression"))
        return _BOUND

    serve_counts(monkeypatch, _count)
    serve_site_search(monkeypatch, SiteSearchResponse())
    bound = bound_values(
        {"text_expression": StringValue(value="erythrocyte surface antigen")},
        infos=_SHEET,
        site_supplied=set(),
        request_texts=[_MESSAGE],
        reason="the model's reason",
        requirement_phrases=_REQUIREMENTS,
    )

    await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="piroplasmadb",
            record_type="transcript",
            search_name="GenesByText",
            params={name: held.value for name, held in bound.items()},
            count=_BOUND,
        ),
        values=bound,
        infos=_SHEET,
    )

    assert (bound["text_expression"].source, counted) == (
        "chosen",
        ['"erythrocyte surface antigen"'],
    )
