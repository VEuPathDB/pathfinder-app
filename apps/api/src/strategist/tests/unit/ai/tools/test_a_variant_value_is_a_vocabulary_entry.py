"""A comparison variant takes the entries its search's vocabulary holds.

A value in another case is the entry it names, a value the vocabulary lacks is
refused unless the step running the search holds it,
a word for every entry runs every entry of a multi-pick, a pick the variant
does not name runs at the site's published default, an empty pick the
parameter does not allow is refused, a search no
step runs is refused with each step's search, before any report runs, and a
variant runs under the record type the catalog lists its search under.
"""

from __future__ import annotations

import json

import pytest
from pydantic_ai import Tool
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import (
    ParameterInfo,
    format_param_info_typed,
)

from strategist.ai.tools.standalone.variant_comparison import compare_search_variants
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import (
    VariantComparison,
    VariantInput,
    VariantResult,
    VariantSpec,
)
from strategist.tests._support.recorded_searches import (
    serve_stated_reads,
    suite_search,
)
from strategist.tests._support.run_context import lead_run_context

# The recorded plasmodb GenesByText, whose Fields vocabulary holds 26 entries.
_TEXT = suite_search("search_genes_by_text")
# The recorded plasmodb GenesByVariantCharacteristics, whose organism allows no pick.
_VARIANTS = suite_search("search_genes_by_variant_characteristics")
_RECORDED = {d.url_segment: d for d in (_TEXT, _VARIANTS)}
_ORGANISM = "Plasmodium falciparum 3D7"
_FIELDS_TAKE = "GenesByText: text_fields takes a list of terms from"
_READ_ENTRIES = (
    "Read its entries with get_parameter_options and pass one of them exactly."
)


contexts: list[dict[str, str]] = []
read_under: list[str] = []


async def _text_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id
    contexts.append(context)
    read_under.append(record_type)
    return format_param_info_typed(list(_RECORDED[search_name].parameters or []))


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

    monkeypatch.setattr(variant_comparison, "search_parameters", _text_parameters)

    serve_stated_reads(monkeypatch, list(_RECORDED.values()))
    monkeypatch.setattr(variant_comparison, "run_variant_comparison", _run)
    return specs


def _variant(label: str, fields: object) -> VariantInput:
    """A GenesByText variant; ``None`` names no Fields value at all."""
    parameters: dict[str, object] = {
        "document_type": "gene",
        "text_expression": '"polar tube protein"',
        "text_search_organism": [_ORGANISM],
    }
    if fields is not None:
        parameters["text_fields"] = fields
    return VariantInput.model_validate(
        {"label": label, "searchName": "GenesByText", "parameters": parameters}
    )


def _product_only() -> VariantInput:
    return _variant(
        "product field (strategy)",
        ["product"],
    )


async def test_a_value_in_another_case_is_refused_with_the_terms(
    ran: list[VariantSpec],
) -> None:
    notes = _variant("product and notes fields", ["product", "notes"])

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [_product_only(), notes])

    assert ran == []
    assert refused.value.message.startswith(_FIELDS_TAKE)
    assert "'Notes'" in refused.value.message


async def test_an_entry_runs_as_named_under_its_parents(
    ran: list[VariantSpec],
) -> None:
    notes = _variant("product and notes fields", ["product", "Notes"])

    await compare_search_variants(lead_run_context(), [_product_only(), notes])

    assert ran[1].parameters["text_fields"] == MultiPickValue(
        values=["product", "Notes"]
    )
    assert {"document_type": "gene"} in contexts


async def test_a_value_the_vocabulary_lacks_is_refused_and_sent_to_its_entries(
    ran: list[VariantSpec],
) -> None:
    guessed = _variant("All text fields", ["product", "gene_name"])

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [_product_only(), guessed])

    assert ran == []
    assert refused.value.message.startswith(_FIELDS_TAKE)


# The published default of text_fields on the recorded sheet: every field.
_EVERY_FIELD = MultiPickValue(
    values=json.loads(
        next(
            p for p in _TEXT.parameters or [] if p.name == "text_fields"
        ).initial_display_value
        or ""
    )
)


async def test_an_absent_pick_runs_at_the_sites_published_default(
    ran: list[VariantSpec],
) -> None:
    absent = _variant("All available text fields", None)

    await compare_search_variants(lead_run_context(), [_product_only(), absent])

    assert ran[0].parameters["text_fields"] == MultiPickValue(values=["product"])
    assert ran[1].parameters["text_fields"] == _EVERY_FIELD
    assert len(_EVERY_FIELD.values) == 26
    assert "text_search_organism" in ran[1].parameters


async def test_an_empty_pick_the_parameter_does_not_allow_is_refused(
    ran: list[VariantSpec],
) -> None:
    empty = _variant("All text fields", [])

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [empty, _product_only()])

    assert ran == []
    assert refused.value.message == (
        "GenesByText: text_fields takes a value, not the empty value []. "
        "Nothing was written."
    )


async def test_a_word_for_every_organism_runs_every_entry(
    ran: list[VariantSpec],
) -> None:
    every = _variant("Every organism", ["product"])
    every.parameters["text_search_organism"] = ["All"]

    await compare_search_variants(lead_run_context(), [_product_only(), every])

    organisms = next(
        p for p in _TEXT.parameters or [] if p.name == "text_search_organism"
    )
    every_entry = [
        o.value for o in format_param_info_typed([organisms])[0].vocabulary()
    ]
    assert ran[1].parameters["text_search_organism"] == MultiPickValue(
        values=every_entry
    )


async def test_a_word_that_is_no_organism_is_refused_and_sent_to_its_entries(
    ran: list[VariantSpec],
) -> None:
    some = _variant("Some organisms", ["product"])
    some.parameters["text_search_organism"] = ["some"]

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [_product_only(), some])

    assert ran == []
    assert refused.value.message == (
        "text_search_organism on GenesByText has no entry that states ['some']. "
        f"{_READ_ENTRIES}"
    )


def _text_step(organisms: list[str]) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="polar tube", site_id="plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters={"text_search_organism": MultiPickValue(values=organisms)},
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


async def test_a_value_the_step_holds_runs_as_the_step_holds_it(
    ran: list[VariantSpec], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step's own value is the site's, whatever the vocabulary read shows."""

    async def _as_run(
        site_id: str,
        comparison: VariantComparison,
        specs: list[VariantSpec],
        *,
        strategy: StrategyAst,
        steps: dict[str, str],
    ) -> VariantComparison:
        del site_id, specs, strategy, steps
        return comparison

    monkeypatch.setattr(variant_comparison, "counted_in_place", _as_run)
    held = _variant("as built", ["product"])
    held.parameters["text_search_organism"] = ["n/a"]

    await compare_search_variants(
        lead_run_context(strategy_session=_text_step(["n/a"])),
        [held, _product_only()],
    )

    assert [v.parameters["text_search_organism"] for v in ran] == [
        MultiPickValue(values=["n/a"]),
        MultiPickValue(values=[_ORGANISM]),
    ]


async def test_a_search_no_step_runs_is_refused_with_each_steps_search(
    ran: list[VariantSpec],
) -> None:
    other = VariantInput(label="by taxon", search_name="GenesByTaxon", parameters={})

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(
            lead_run_context(strategy_session=_text_step([_ORGANISM])),
            [other, _product_only()],
        )

    assert ran == []
    assert refused.value.message.startswith(
        "GenesByTaxon (by taxon) is no search a step of this strategy runs"
    )
    assert "The steps: step_text runs GenesByText." in refused.value.message


async def test_a_variant_runs_under_the_record_type_its_search_is_listed_under(
    ran: list[VariantSpec],
) -> None:
    """A record type the caller states is no input; the catalog's is the one run."""
    stated = VariantInput.model_validate(
        {
            "label": "gene records",
            "recordType": "gene",
            "searchName": "GenesByText",
            "parameters": {
                "text_fields": ["product"],
                "text_expression": '"signal peptide"',
                "text_search_organism": [_ORGANISM],
            },
        }
    )
    read_under.clear()

    await compare_search_variants(lead_run_context(), [stated, _product_only()])

    assert [(v.label, v.record_type) for v in ran] == [
        ("gene records", "transcript"),
        ("product field (strategy)", "transcript"),
    ]
    assert set(read_under) == {"transcript"}


async def test_a_search_the_catalog_does_not_list_is_refused_with_the_nearest(
    ran: list[VariantSpec],
) -> None:
    unlisted = VariantInput(label="typo", search_name="GenesByTexts", parameters={})

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [unlisted, _product_only()])

    assert ran == []
    assert refused.value.message.startswith(
        "plasmodb lists no search GenesByTexts (typo). Nearest searches: GenesByText"
    )


def test_the_comparison_takes_no_record_type_from_the_caller() -> None:
    schema = Tool(compare_search_variants).tool_def.parameters_json_schema

    assert schema["properties"]["variants"]["items"] == {"$ref": "#/$defs/VariantInput"}
    assert list(schema["$defs"]["VariantInput"]["properties"]) == [
        "label",
        "searchName",
        "parameters",
    ]


async def test_an_empty_pick_the_parameter_allows_is_sent_empty(
    ran: list[VariantSpec],
) -> None:
    def organisms(label: str, picked: list[str]) -> VariantInput:
        return VariantInput.model_validate(
            {
                "label": label,
                "searchName": "GenesByVariantCharacteristics",
                "parameters": {"organism_select_none": picked},
            }
        )

    await compare_search_variants(
        lead_run_context(),
        [organisms("no organism", []), organisms("falciparum", [_ORGANISM])],
    )

    assert ran[0].parameters["organism_select_none"] == MultiPickValue(values=[])
