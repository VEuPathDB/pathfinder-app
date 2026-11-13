"""A text the linked requirement's quote writes otherwise is chosen, not
stated, and the quote it was cut from is never a reading."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.wdk import SiteSearchResponse
from veupathdb_mcp.catalog import format_param_info_typed

from strategist.ai.tools.standalone._frame_sources import bound_values, quotes_by_param
from strategist.domain.strategy.constraints import Constraint, ConstraintKind
from strategist.domain.strategy.operational_spec import RequirementLink
from strategist.domain.strategy.value_source import cut_from
from strategist.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from strategist.tests._support.recorded_counts import (
    serve_counts,
    serve_site_search,
    wire,
)
from strategist.tests._support.recorded_searches import suite_search

_MESSAGE = (
    "Babesia bovis T2Bo genes with a variant erythrocyte surface antigen annotation."
)
_QUOTE = "variant erythrocyte surface antigen"
_SHEET = format_param_info_typed(
    suite_search("search_giardiadb_genes_by_text").parameters or []
)


def _source(text: str, message: str, quotes: list[str]) -> str:
    bound = bound_values(
        {"text_expression": StringValue(value=text)},
        infos=_SHEET,
        site_supplied=set(),
        request_texts=[message],
        reason="the model's reason",
        linked_quotes={"text_expression": quotes},
    )
    return bound["text_expression"].source


def test_a_text_cut_from_the_linked_quote_is_chosen() -> None:
    assert (
        _source("erythrocyte surface antigen", _MESSAGE, [_QUOTE]),
        cut_from(StringValue(value="erythrocyte surface antigen"), [_QUOTE]),
    ) == ("chosen", True)


def test_the_text_the_linked_quote_writes_stays_stated() -> None:
    assert (
        _source(f'"{_QUOTE}"', _MESSAGE, [_QUOTE]),
        cut_from(StringValue(value=f'"{_QUOTE}"'), [_QUOTE.upper()]),
    ) == ("stated", False)


def test_a_text_no_requirement_links_keeps_its_source() -> None:
    assert _source("erythrocyte surface antigen", _MESSAGE, []) == "stated"


def test_a_quote_linked_to_another_parameter_cuts_nothing() -> None:
    bound = bound_values(
        {"text_expression": StringValue(value="erythrocyte surface antigen")},
        infos=_SHEET,
        site_supplied=set(),
        request_texts=[_MESSAGE],
        reason="the model's reason",
        linked_quotes={"text_fields": [_QUOTE]},
    )

    assert bound["text_expression"].source == "stated"


def test_only_a_text_is_cut() -> None:
    assert cut_from(MultiPickValue(values=["erythrocyte"]), [_QUOTE]) is False


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
        linked_quotes={"text_expression": [_QUOTE]},
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


def test_each_parameter_takes_the_quotes_of_the_requirements_linked_to_it() -> None:
    linked = Constraint(
        kind=ConstraintKind.UNTYPED,
        requested_value="variant erythrocyte surface antigen",
        label="annotation",
        quote=_QUOTE,
    )
    unquoted = Constraint(
        kind=ConstraintKind.ORGANISM, requested_value="Babesia bovis T2Bo", label="o"
    )

    assert quotes_by_param(
        [
            RequirementLink(requirement=linked.id, param="text_expression"),
            RequirementLink(requirement=unquoted.id, param="organism"),
            RequirementLink(requirement=linked.id),
        ],
        [linked, unquoted],
    ) == {"text_expression": [_QUOTE]}
