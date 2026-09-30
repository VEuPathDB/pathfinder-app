"""A comparison variant takes the entries its search's vocabulary holds.

A value in another case is the entry it names, a value the vocabulary lacks is
refused with the nearest entries, and an empty pick is refused with the whole
vocabulary, before any report runs.
"""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.tools.standalone import _variant_targets
from pathfinder.ai.tools.standalone.variant_comparison import compare_search_variants
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import (
    VariantComparison,
    VariantResult,
    VariantSpec,
)
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.run_context import lead_run_context

# The recorded plasmodb GenesByText, whose Fields vocabulary holds 26 entries.
_TEXT = suite_search("search_genes_by_text")
_ORGANISM = "Plasmodium falciparum 3D7"


contexts: list[dict[str, str]] = []


async def _text_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type
    assert search_name == "GenesByText"
    contexts.append(context)
    return format_param_info_typed(list(_TEXT.parameters or []))


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[VariantSpec]:
    specs: list[VariantSpec] = []

    async def _run(site_id: str, given: list[VariantSpec]) -> VariantComparison:
        del site_id
        specs.extend(given)
        return VariantComparison(
            variants=[
                VariantResult(
                    label=s.label,
                    search_name=s.search_name,
                    gene_count=1,
                    unique_count=0,
                    sample_unique_genes=[],
                )
                for s in given
            ],
            overlaps=[],
        )

    async def _details(ctx: SearchContext) -> tuple[WDKSearchResponse, str]:
        assert ctx.search_name == "GenesByText"
        body = {
            "searchData": _TEXT.model_dump(by_alias=True, mode="json"),
            "validation": {"level": "DISPLAYABLE", "isValid": True},
        }
        return WDKSearchResponse.model_validate(body), "transcript"

    monkeypatch.setattr(variant_comparison, "search_parameters", _text_parameters)
    monkeypatch.setattr(_variant_targets, "fetch_search_details", _details)
    monkeypatch.setattr(variant_comparison, "run_variant_comparison", _run)
    return specs


def _variant(label: str, fields: object) -> VariantSpec:
    return VariantSpec.model_validate(
        {
            "label": label,
            "searchName": "GenesByText",
            "parameters": {
                "document_type": {"type": "string", "value": "gene"},
                "text_expression": {"type": "string", "value": '"polar tube protein"'},
                "text_search_organism": {"type": "string", "value": f'["{_ORGANISM}"]'},
                "text_fields": fields,
            },
        }
    )


def _product_only() -> VariantSpec:
    return _variant(
        "product field (strategy)",
        {"type": "multi-pick-vocabulary", "values": ["product"]},
    )


async def test_a_value_in_another_case_runs_as_the_entry_it_names(
    ran: list[VariantSpec],
) -> None:
    notes = _variant(
        "product and notes fields",
        {"type": "multi-pick-vocabulary", "values": ["product", "notes"]},
    )

    await compare_search_variants(lead_run_context(), [_product_only(), notes])

    assert ran[1].parameters["text_fields"] == MultiPickValue(
        values=["product", "Notes"]
    )
    assert {"document_type": "gene"} in contexts


async def test_a_value_the_vocabulary_lacks_is_refused_with_the_nearest_entries(
    ran: list[VariantSpec],
) -> None:
    guessed = _variant(
        "All text fields",
        {"type": "string", "value": '["product","gene_name","notes","description"]'},
    )

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [_product_only(), guessed])

    assert ran == []
    message = refused.value.message
    assert message.startswith(
        "text_fields on GenesByText has no entry matching ['gene_name', 'description']."
    )
    assert "Nearest entries:" in message


async def test_an_empty_pick_is_refused_with_the_whole_vocabulary(
    ran: list[VariantSpec],
) -> None:
    empty = _variant("All text fields", {"type": "string", "value": "[]"})

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [empty, _product_only()])

    assert ran == []
    message = refused.value.message
    assert message.startswith(
        "text_fields on GenesByText takes at least one entry (All text fields), and "
        "the site refuses an empty pick. Its vocabulary holds 26 entries: "
        "apolloCommentContent, ECNumbers,"
    )
    assert "Notes, organism_full" in message
    assert message.endswith("GeneTranscripts, UserCommentContent.")
