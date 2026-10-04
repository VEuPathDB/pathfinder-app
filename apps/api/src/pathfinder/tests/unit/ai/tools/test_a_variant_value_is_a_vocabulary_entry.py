"""A comparison variant takes the entries its search's vocabulary holds.

A value in another case is the entry it names, a value the vocabulary lacks is
refused with the nearest entries unless the step running the search holds it,
a word for every entry runs every entry of a multi-pick, a pick that names no
entry runs at the site's published default, a search no
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

from pathfinder.ai.tools.standalone.variant_comparison import compare_search_variants
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import (
    VariantComparison,
    VariantInput,
    VariantResult,
    VariantSpec,
)
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.run_context import lead_run_context

# The recorded plasmodb GenesByText, whose Fields vocabulary holds 26 entries.
_TEXT = suite_search("search_genes_by_text")
_ORGANISM = "Plasmodium falciparum 3D7"


contexts: list[dict[str, str]] = []
read_under: list[str] = []


async def _text_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id
    assert search_name == "GenesByText"
    contexts.append(context)
    read_under.append(record_type)
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

    monkeypatch.setattr(variant_comparison, "search_parameters", _text_parameters)
    monkeypatch.setattr(variant_comparison, "run_variant_comparison", _run)
    return specs


def _variant(label: str, fields: object) -> VariantInput:
    """A GenesByText variant; ``None`` names no Fields value at all."""
    parameters: dict[str, object] = {
        "document_type": {"type": "string", "value": "gene"},
        "text_expression": {"type": "string", "value": '"polar tube protein"'},
        "text_search_organism": {"type": "string", "value": f'["{_ORGANISM}"]'},
    }
    if fields is not None:
        parameters["text_fields"] = fields
    return VariantInput.model_validate(
        {"label": label, "searchName": "GenesByText", "parameters": parameters}
    )


def _product_only() -> VariantInput:
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


async def test_an_empty_pick_runs_at_the_sites_published_default(
    ran: list[VariantSpec],
) -> None:
    empty = _variant("All text fields", {"type": "string", "value": "[]"})

    await compare_search_variants(lead_run_context(), [empty, _product_only()])

    assert ran[0].parameters["text_fields"] == _EVERY_FIELD


async def test_an_empty_pick_with_no_default_is_refused_with_the_vocabulary(
    ran: list[VariantSpec],
) -> None:
    """The recorded Organism default takes no entry, so the site refuses it."""
    no_organism = _variant(
        "no organism", {"type": "multi-pick-vocabulary", "values": ["product"]}
    )
    no_organism.parameters["text_search_organism"] = MultiPickValue(values=[])

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(
            lead_run_context(), [no_organism, _product_only()]
        )

    assert ran == []
    assert refused.value.message.startswith(
        "text_search_organism on GenesByText takes at least one entry (no organism), "
        "and the site refuses an empty pick."
    )


async def test_a_word_for_every_field_runs_every_entry(
    ran: list[VariantSpec],
) -> None:
    every = _variant(
        "Every text field", {"type": "multi-pick-vocabulary", "values": ["All"]}
    )

    await compare_search_variants(lead_run_context(), [_product_only(), every])

    fields = next(p for p in _TEXT.parameters or [] if p.name == "text_fields")
    every_entry = [o.value for o in format_param_info_typed([fields])[0].vocabulary()]
    assert len(every_entry) == 26
    assert ran[1].parameters["text_fields"] == MultiPickValue(values=every_entry)


async def test_a_word_that_is_no_entry_is_refused_with_the_nearest_entries(
    ran: list[VariantSpec],
) -> None:
    some = _variant(
        "Some text fields", {"type": "multi-pick-vocabulary", "values": ["some"]}
    )

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(lead_run_context(), [_product_only(), some])

    assert ran == []
    assert refused.value.message.startswith(
        "text_fields on GenesByText has no entry matching ['some']."
    )
    assert "Nearest entries:" in refused.value.message


def _text_step(fields: list[str]) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="polar tube", site_id="plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters={"text_fields": MultiPickValue(values=fields)},
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
    held = _variant("as built", {"type": "multi-pick-vocabulary", "values": ["n/a"]})

    await compare_search_variants(
        lead_run_context(strategy_session=_text_step(["n/a"])),
        [held, _product_only()],
    )

    assert [v.parameters["text_fields"] for v in ran] == [
        MultiPickValue(values=["n/a"]),
        MultiPickValue(values=["product"]),
    ]


async def test_a_search_no_step_runs_is_refused_with_each_steps_search(
    ran: list[VariantSpec],
) -> None:
    other = VariantInput(label="by taxon", search_name="GenesByTaxon", parameters={})

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(
            lead_run_context(strategy_session=_text_step(["product"])),
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
                "text_fields": {"type": "string", "value": '["product"]'},
                "text_expression": {"type": "string", "value": '"signal peptide"'},
                "text_search_organism": {
                    "type": "string",
                    "value": f'["{_ORGANISM}"]',
                },
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
