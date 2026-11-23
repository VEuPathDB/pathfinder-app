"""A variant sends what a step of its search sends: every parameter it names no
value for at the value the site's sheet gives it, and each hidden parameter at
the value the site sets, one it names replaced."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import HeldValue, ParamValue, StringValue, shown_stated
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ParameterInfo, ResolveContext

from strategist.ai.tools.standalone._variant_targets import resolved_variants
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import VariantInput
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.record_classes import (
    list_searches_under,
    serve_record_classes,
)
from strategist.tests._support.recorded_searches import (
    client_search,
    serve_stated_reads,
    suite_search,
)

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
    return sheet_of(list(search.parameters or []))


@pytest.fixture(autouse=True)
def _recorded_text_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _text_parameters)
    serve_stated_reads(monkeypatch, [_TEXT, _LOCATION])
    serve_record_classes(monkeypatch)
    list_searches_under(monkeypatch, "transcript", ["GenesByLocation"])


def _text_search(**extra: object) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "signal peptide in product",
            "searchName": "GenesByText",
            "parameters": {
                "text_expression": "signal peptide",
                "text_fields": ["product"],
                "text_search_organism": ["Plasmodium falciparum 3D7"],
                **extra,
            },
        }
    )


async def test_a_hidden_parameter_the_variant_leaves_out_runs_at_the_sites_value() -> (
    None
):
    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"),
        [_text_search()],
        ResolveContext(site_id="plasmodb"),
    )

    assert spec.parameters["document_type"] == StringValue(value="gene")


async def test_a_value_named_for_a_hidden_parameter_is_replaced_by_the_sites() -> None:
    named = _text_search(document_type="transcript")

    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"), [named], ResolveContext(site_id="plasmodb")
    )

    assert spec.parameters["document_type"] == StringValue(value="gene")


def _location(**values: object) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "chromosome 4",
            "searchName": "GenesByLocation",
            "parameters": {
                "organismSinglePick": ["Plasmodium falciparum 3D7"],
                **values,
            },
        }
    )


async def test_a_parameter_the_variant_leaves_out_runs_at_the_sheets_value() -> None:
    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"),
        [_location()],
        ResolveContext(site_id="plasmodb"),
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
    named = _location(start_point="100000")

    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"), [named], ResolveContext(site_id="plasmodb")
    )

    assert spec.parameters["start_point"] == StringValue(value="100000")


def _held_text_step(fields: ParamValue) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "text", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="text",
            search_name="GenesByText",
            parameters={
                "text_expression": StringValue(value="kinase"),
                "text_fields": fields,
            },
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


async def test_a_kept_value_stated_back_as_shown_is_sent_as_held() -> None:
    held = HeldValue(wire="product,notes")
    variant = _text_search(text_fields=shown_stated(held))

    (spec,) = await resolved_variants(
        _held_text_step(held), [variant], ResolveContext(site_id="plasmodb")
    )

    assert spec.parameters["text_fields"] == held
