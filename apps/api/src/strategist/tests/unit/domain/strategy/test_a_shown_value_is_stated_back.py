from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import (
    KEPT_MARK,
    FilterFacets,
    FilterProposals,
    FilterValue,
    HeldValue,
    NumberMembers,
    ParamValue,
    StringValue,
    from_wire,
)
from veupathdb.wdk import WDKParameter, WDKSearch

from strategist.domain.strategy.expression_handles import (
    expression_handle,
    resolved_params,
    stated_text,
    stated_value,
)
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.domain.strategy.spec_diff import diff_specs
from strategist.domain.strategy.value_text import clause_text
from strategist.tests._support.bound_values import bound
from strategist.tests._support.recorded_searches import suite_search

_VALUE: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)
_SNPS = suite_search("search_genes_by_ngs_snps")
_VARIANTS = suite_search("search_genes_by_variant_characteristics")
_TAXON = suite_search("search_genes_by_taxon")
_EXPRESSION = "pfal>=1T AND hsap=0T"


def _declared(search: WDKSearch, name: str) -> WDKParameter:
    return next(p for p in search.parameters or [] if p.name == name)


def _read_back(search: WDKSearch, name: str, value: ParamValue) -> str:
    declared = _declared(search, name)
    read = declared.read_stated(stated_value(name, value))
    match read:
        case FilterProposals():
            return FilterFacets.of(declared).bind(read).to_wire()
        case _:
            return _VALUE.validate_python(read).to_wire()


_HELD: list[tuple[WDKSearch, str, str]] = [
    (_SNPS, "organismSinglePick", '["Plasmodium vivax P01"]'),
    (_SNPS, "MinPercentMinorAlleles", "5.0"),
    (_TAXON, "organism", '["Plasmodium falciparum 3D7"]'),
    (_VARIANTS, "organism_select_none", '["Plasmodium falciparum 3D7"]'),
    (
        _VARIANTS,
        "gene_variant_stats",
        (
            '{"filters": [{"field": "total_variants", "type": "number", '
            '"isRange": true, "includeUnknown": false, "value": {"min": 1.0}}]}'
        ),
    ),
]


@pytest.mark.parametrize(("search", "name", "wire"), _HELD)
def test_a_shown_value_reads_back_to_the_wire_it_holds(
    search: WDKSearch, name: str, wire: str
) -> None:
    value = from_wire(_declared(search, name).type, wire)

    assert _read_back(search, name, value) == value.to_wire()


def test_a_filter_is_shown_as_its_clauses() -> None:
    value = from_wire("filter", _HELD[-1][2])

    assert stated_value("gene_variant_stats", value) == [
        {"field": "total_variants", "value": {"min": 1.0}}
    ]


def test_an_expression_is_shown_by_its_handle_that_maps_back() -> None:
    shown = stated_value("phyletic_expression", StringValue(value=_EXPRESSION))

    assert shown == expression_handle(_EXPRESSION)
    assert resolved_params(
        {"phyletic_expression": str(shown)},
        {expression_handle(_EXPRESSION): _EXPRESSION},
    ) == {"phyletic_expression": _EXPRESSION}


def test_a_kept_value_is_shown_marked_in_a_field_and_in_prose() -> None:
    kept = f"'a,b' {KEPT_MARK}"

    assert stated_value("x", HeldValue(wire="a,b")) == kept
    assert stated_text("x", HeldValue(wire="a,b")) == kept


def test_a_filter_with_no_clause_is_shown_as_no_clause() -> None:
    assert stated_value("variation_sample_meta", FilterValue()) == []
    assert stated_text("variation_sample_meta", FilterValue()) == "[]"


def test_a_pick_is_shown_in_prose_as_its_stated_list() -> None:
    value = from_wire("multi-pick-vocabulary", '["Plasmodium vivax P01"]')

    assert stated_text("organismSinglePick", value) == '["Plasmodium vivax P01"]'


def test_a_number_text_restated_as_shown_moves_nothing() -> None:
    held = from_wire("string", "5.0")
    declared = _declared(_SNPS, "MinPercentMinorAlleles")
    restated = _VALUE.validate_python(
        declared.read_stated(stated_value("MinPercentMinorAlleles", held))
    )

    def _spec(value: ParamValue) -> OperationalSpec:
        return OperationalSpec(
            criteria=[
                Criterion(
                    id="c_snps",
                    text="SNPs",
                    search_name="GenesByNgsSnps",
                    resolved_params=bound({"MinPercentMinorAlleles": value}),
                )
            ]
        )

    assert restated.to_wire() == "5.0"
    [change] = diff_specs(
        _spec(held), _spec(restated), sets_the_site=lambda _s, _p: False
    ).changes
    assert (change.disposition, change.changed_params) == ("kept", {})


def test_a_number_member_spelled_as_text_is_shown_as_written() -> None:
    clause = NumberMembers.model_validate(
        {
            "field": "count",
            "type": "number",
            "isRange": False,
            "includeUnknown": False,
            "value": ["1.50", 3],
        }
    )

    assert clause_text(clause) == "count: 1.50, 3"
