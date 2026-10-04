"""A variant sends what a step of its search sends: every parameter it names no
value for at the value the site's sheet gives it, and each hidden parameter at
the value the site sets, one it names replaced."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.tools.standalone._variant_targets import resolved_variants
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import VariantInput
from pathfinder.tests._support.record_classes import (
    list_searches_under,
    serve_record_classes,
)
from pathfinder.tests._support.recorded_searches import client_search, suite_search

# The recorded plasmodb GenesByText, whose hidden document_type the site sets to gene.
_TEXT = suite_search("search_genes_by_text")
# The recorded plasmodb GenesByLocation, whose optional sequenceId the sheet gives
# its placeholder.
_LOCATION = client_search("search_genes_by_location")


async def _text_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, context
    search = _LOCATION if search_name == "GenesByLocation" else _TEXT
    return format_param_info_typed(list(search.parameters or []))


@pytest.fixture(autouse=True)
def _recorded_text_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _text_parameters)
    serve_record_classes(monkeypatch)
    list_searches_under(monkeypatch, "transcript", ["GenesByLocation"])


def _text_search(**extra: object) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "signal peptide in product",
            "searchName": "GenesByText",
            "parameters": {
                "text_expression": {"type": "string", "value": "signal peptide"},
                "text_fields": {"type": "multi-pick-vocabulary", "values": ["product"]},
                **extra,
            },
        }
    )


async def test_a_hidden_parameter_the_variant_leaves_out_runs_at_the_sites_value() -> (
    None
):
    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"), [_text_search()]
    )

    assert spec.parameters["document_type"] == StringValue(value="gene")


async def test_a_value_named_for_a_hidden_parameter_is_replaced_by_the_sites() -> None:
    named = _text_search(document_type={"type": "string", "value": "transcript"})

    (spec,) = await resolved_variants(StrategySession(site_id="plasmodb"), [named])

    assert spec.parameters["document_type"] == StringValue(value="gene")


def _location(**values: object) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "chromosome 4",
            "searchName": "GenesByLocation",
            "parameters": {
                "organismSinglePick": {
                    "type": "multi-pick-vocabulary",
                    "values": ["Plasmodium falciparum 3D7"],
                },
                **values,
            },
        }
    )


async def test_a_parameter_the_variant_leaves_out_runs_at_the_sheets_value() -> None:
    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"), [_location()]
    )

    assert {
        name: spec.parameters[name]
        for name in ("sequenceId", "start_point", "end_point")
    } == {
        "sequenceId": StringValue(value="(Example: Pf3D7_04_v3)"),
        "start_point": StringValue(value="1"),
        "end_point": StringValue(value="0"),
    }


async def test_a_value_the_variant_names_is_sent_as_named() -> None:
    named = _location(start_point={"type": "string", "value": "100000"})

    (spec,) = await resolved_variants(StrategySession(site_id="plasmodb"), [named])

    assert spec.parameters["start_point"] == StringValue(value="100000")
