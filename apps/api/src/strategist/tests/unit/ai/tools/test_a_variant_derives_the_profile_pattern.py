"""A variant of the orthology profile search runs the pattern its two species
lists derive, as a step of that search does."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import StringValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from strategist.ai.tools.standalone._variant_targets import resolved_variants
from strategist.domain.strategy.session import StrategySession
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import VariantInput
from strategist.tests._support.record_classes import (
    list_searches_under,
    serve_record_classes,
)
from strategist.tests._support.recorded_searches import suite_search

_PROFILE = suite_search("search_genes_by_ortholog_pattern")


async def _profile_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, search_name, context
    return format_param_info_typed(list(_PROFILE.parameters or []))


async def _profile_definition(
    site_id: str, record_type: str, search_name: str
) -> WDKSearch:
    del site_id, record_type, search_name
    return _PROFILE


@pytest.fixture(autouse=True)
def _recorded_profile_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _profile_parameters)
    monkeypatch.setattr(
        variant_comparison, "read_search_definition", _profile_definition
    )
    serve_record_classes(monkeypatch)
    list_searches_under(monkeypatch, "transcript", ["GenesByOrthologPattern"])


def _profile(**lists: str) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "in falciparum, not in human",
            "searchName": "GenesByOrthologPattern",
            "parameters": {
                name: {"type": "string", "value": value}
                for name, value in lists.items()
            },
        }
    )


async def test_the_species_lists_derive_the_pattern_the_variant_runs() -> None:
    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"),
        [_profile(included_species="pfal", excluded_species="hsap")],
    )

    assert spec.parameters["profile_pattern"] == StringValue(value="%hsap:N%pfal:Y%")


async def test_a_variant_naming_no_species_is_refused() -> None:
    with pytest.raises(ModelRetry, match="included_species"):
        await resolved_variants(StrategySession(site_id="plasmodb"), [_profile()])


async def test_a_comma_list_of_species_codes_derives_one_pattern() -> None:
    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"),
        [_profile(included_species="pfal", excluded_species="hsap,pber")],
    )

    assert spec.parameters["profile_pattern"] == StringValue(
        value="%hsap:N%pber:N%pfal:Y%"
    )
