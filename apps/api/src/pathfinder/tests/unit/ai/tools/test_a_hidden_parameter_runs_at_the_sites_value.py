"""A variant runs each hidden parameter at the value the site sets: one the
variant leaves out is filled, and one it names is replaced."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.tools.standalone._variant_targets import resolved_variants
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import VariantInput
from pathfinder.tests._support.record_classes import serve_record_classes
from pathfinder.tests._support.recorded_searches import suite_search

# The recorded plasmodb GenesByText, whose hidden document_type the site sets to gene.
_TEXT = suite_search("search_genes_by_text")


async def _text_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, search_name, context
    return format_param_info_typed(list(_TEXT.parameters or []))


@pytest.fixture(autouse=True)
def _recorded_text_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _text_parameters)
    serve_record_classes(monkeypatch)


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
