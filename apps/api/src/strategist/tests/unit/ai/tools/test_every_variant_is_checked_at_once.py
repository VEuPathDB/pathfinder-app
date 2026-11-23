from __future__ import annotations

import pytest
from veupathdb.domain.parameters import to_wire
from veupathdb_mcp.catalog import ParameterInfo, ResolveContext

from strategist.ai.tools.standalone._variant_targets import (
    checked_variants,
    resolved_variants,
)
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

    with pytest.raises(ProblemsRefusal) as refused:
        await resolved_variants(
            StrategySession(site_id="plasmodb"),
            [taxon],
            ResolveContext(site_id="plasmodb"),
        )

    assert [p.sentence for p in refused.value.problems.found] == [
        "all genes: GenesByTaxon requires Organism; state a value."
    ]


def _weighted(label: str, search_name: str) -> VariantInput:
    return VariantInput.model_validate(
        {"label": label, "searchName": search_name, "parameters": {"weight": 2}}
    )


async def test_a_comparison_names_the_steps_once_for_every_unknown_parameter() -> None:
    with pytest.raises(ProblemsRefusal) as refused:
        await checked_variants(
            StrategySession(site_id="plasmodb"),
            [_weighted("text", "GenesByText"), _weighted("taxon", "GenesByTaxon")],
            ResolveContext(site_id="plasmodb"),
        )

    sentences = [problem.sentence for problem in refused.value.problems.found]
    assert [s.startswith(("GenesByText", "GenesByTaxon")) for s in sentences] == [
        True,
        True,
        False,
    ]
    assert str(refused.value).count("never a parameter") == 1


async def test_a_search_counted_alone_is_not_told_about_steps() -> None:
    with pytest.raises(ProblemsRefusal) as refused:
        await resolved_variants(
            StrategySession(site_id="plasmodb"),
            [_weighted("text", "GenesByText"), _weighted("taxon", "GenesByTaxon")],
            ResolveContext(site_id="plasmodb"),
        )

    assert [p.key.search for p in refused.value.problems.found] == [
        "GenesByText",
        "GenesByTaxon",
    ]
    assert "never a parameter" not in str(refused.value)


async def _term_under_fields(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, search_name
    term = "kinase" if "text_fields" in context else None
    changed: dict[str, dict[str, object]] = {
        "text_fields": {"wire_children": ["text_expression"]},
        "text_expression": {"wire_parents": ["text_fields"], "default_value": term},
    }
    return [
        info.model_copy(update=changed.get(info.name, {}))
        for info in sheet_of(list(_TEXT.parameters or []))
    ]


async def test_a_required_value_its_stated_parent_fills_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _term_under_fields)
    fields = VariantInput.model_validate(
        {
            "label": "by name",
            "searchName": "GenesByText",
            "parameters": {
                "text_search_organism": ["Plasmodium falciparum 3D7"],
                "text_fields": ["name"],
            },
        }
    )

    [spec] = await resolved_variants(
        StrategySession(site_id="plasmodb"),
        [fields],
        ResolveContext(site_id="plasmodb"),
    )

    assert to_wire(spec.parameters["text_expression"]) == "kinase"
