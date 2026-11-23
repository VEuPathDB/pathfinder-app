from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import ParameterInfo, ResolveContext

from strategist.ai.tools.standalone._variant_targets import resolved_variants
from strategist.domain.strategy.session import StrategySession
from strategist.platform.refusals import ProblemsRefusal
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import VariantInput
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.record_classes import (
    list_searches_under,
    serve_record_classes,
)
from strategist.tests._support.recorded_searches import (
    serve_stated_reads,
    suite_search,
)

_TEXT = suite_search("search_genes_by_text")
_TAXON = suite_search("search_genes_by_taxon")


async def _parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, context
    search = _TAXON if search_name == "GenesByTaxon" else _TEXT
    return sheet_of(list(search.parameters or []))


@pytest.fixture(autouse=True)
def _recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _parameters)
    serve_stated_reads(monkeypatch, [_TEXT, _TAXON])
    serve_record_classes(monkeypatch)
    list_searches_under(monkeypatch, "transcript", ["GenesByText", "GenesByTaxon"])


def _text(label: str, fields: list[str]) -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": label,
            "searchName": "GenesByText",
            "parameters": {"text_expression": "kinase", "text_fields": fields},
        }
    )


async def test_two_variants_with_an_unmatched_value_each_are_one_refusal() -> None:
    with pytest.raises(ProblemsRefusal) as refused:
        await resolved_variants(
            StrategySession(site_id="plasmodb"),
            [_text("first", ["nowhere field"]), _text("second", ["elsewhere field"])],
            ResolveContext(site_id="plasmodb"),
        )

    labels = {problem.key.criterion for problem in refused.value.problems.found}
    assert labels == {"first", "second"}


async def test_a_taxon_variant_that_names_no_organism_is_refused() -> None:
    taxon = VariantInput.model_validate(
        {"label": "all genes", "searchName": "GenesByTaxon", "parameters": {}}
    )

    with pytest.raises(ProblemsRefusal, match="requires Organism"):
        await resolved_variants(
            StrategySession(site_id="plasmodb"),
            [taxon],
            ResolveContext(site_id="plasmodb"),
        )
