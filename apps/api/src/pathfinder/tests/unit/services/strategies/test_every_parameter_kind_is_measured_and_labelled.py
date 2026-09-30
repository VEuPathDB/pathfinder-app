"""Every parameter kind WDK publishes has a measurement rule, or states why it
has none, and a label rule; each rule is replayed on a recorded sheet."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import get_args

import pytest
from veupathdb.domain.parameters import (
    FilterValue,
    MultiPickValue,
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.wdk import WDKSearch, phyletic_tree_of
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Measurement,
    ValueSource,
)
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.services.strategies.parameter_rules import (
    PARAMETER_RULES,
    parameter_class,
    rules_of,
    site_fixed,
)
from pathfinder.services.strategies.value_labels import vocabulary_labels
from pathfinder.tests._support.recorded_counts import (
    CRYPTO_IOWA,
    TGON_STRAINS,
    recorded_count,
    serve_counts,
    wire,
)
from pathfinder.tests._support.recorded_searches import suite_search

_TEXT = suite_search("search_genes_by_text")
_PCT = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_ORTHOLOG = suite_search("search_genes_by_ortholog_pattern")
_SNPS = suite_search("search_genes_by_ngs_snps")
_E_CUNICULI = "Encephalitozoon cuniculi GB-M1"
_ALL_FIELDS = (
    '["apolloCommentContent","ECNumbers","Epitopes","GeneLinkouts","primary_key",'
    '"name","gene_type","GeneModelCharacteristics","sequence_id","GOTerms",'
    '"InterPro","MetabolicPathways","Alias","Notes","organism_full","orthomcl_name",'
    '"Orthologs","PdbSimilarities","PhenotypeCategoricalValues","product",'
    '"Products","PubMed","so_id","so_term_name","GeneTranscripts",'
    '"UserCommentContent"]'
)
_FIELDS_NOT_TAKEN = [
    "Apollo Annotations",
    "EC descriptions and numbers",
    "Epitopes from IEDB",
    "External links",
    "Gene ID",
    "Gene name or symbol",
    "Gene type",
    "GeneModel Characteristics",
    "Genomic sequence ID",
    "GO terms",
    "InterPro domains",
    "Metabolic pathways",
    "Names, IDs, and aliases",
    "Organism",
    "Ortholog group",
    "Orthologs",
    "PDB chains",
    "Phenotype values",
    "PubMed",
    "Sequence Ontology ID",
    "Sequence Ontology term",
    "Transcripts",
    "User comments",
]


def _sheet(search: WDKSearch) -> list[ParameterInfo]:
    return format_param_info_typed(list(search.parameters or []))


def _bound(
    params: Mapping[str, ParamValue], sources: Mapping[str, ValueSource]
) -> dict[str, BoundValue]:
    return {
        name: BoundValue(value=value, source=sources.get(name, "stated"))
        for name, value in params.items()
    }


def test_every_parameter_kind_has_a_rule() -> None:
    kinds = set(get_args(ParamKind))

    assert kinds <= set(PARAMETER_RULES)
    assert {
        name: rules.reason
        for name, rules in PARAMETER_RULES.items()
        if rules.measurement == "not_measurable"
    } == {
        "date": "the site publishes no bound to read a date at",
        "date-range": "the site publishes no bound to read a date at",
        "timestamp": "the site publishes no bound to read a date at",
        "input-dataset": "an uploaded dataset has no other reading",
        "input-step": "a step input is another step's result",
        "phyletic_pattern": "the pattern is derived from the species lists",
    }


def test_every_parameter_class_has_a_source_rule() -> None:
    assert {
        name: rules.source
        for name, rules in PARAMETER_RULES.items()
        if rules.source != "words"
    } == {"site_fixed": "site"}


def test_a_read_only_parameter_is_set_by_the_site() -> None:
    text = {info.name: info for info in _sheet(_TEXT)}

    assert (
        rules_of(text["document_type"]).source,
        rules_of(text["text_expression"]).source,
    ) == ("site", "words")


def test_each_recorded_parameter_has_its_class() -> None:
    classes = {
        info.name: parameter_class(info)
        for search in (_TEXT, _PCT, _ORTHOLOG)
        for info in _sheet(search)
    }

    assert classes == {
        "text_search_organism": "tree_pick",
        "text_expression": "string",
        "document_type": "site_fixed",
        "text_fields": "multi-pick-vocabulary",
        "profileset_generic": "single-pick-vocabulary",
        "samples_percentile_generic": "multi-pick-vocabulary",
        "min_expression_percentile": "numeric_string",
        "max_expression_percentile": "numeric_string",
        "any_or_all": "single-pick-vocabulary",
        "protein_coding_only": "single-pick-vocabulary",
        "channel": "single-pick-vocabulary",
        "profile_pattern": "phyletic_pattern",
        "included_species": "phyletic_list",
        "excluded_species": "phyletic_list",
        "organism": "tree_pick",
    }


def test_only_a_read_only_or_a_hidden_parameter_without_a_vocabulary_is_the_sites() -> (
    None
):
    text = _sheet(_TEXT)
    channel = next(info for info in _sheet(_PCT) if info.name == "channel")

    assert [(i.name, i.is_read_only) for i in text if site_fixed(i)] == [
        ("document_type", True)
    ]
    assert (
        site_fixed(channel),
        site_fixed(channel.model_copy(update={"is_read_only": True})),
    ) == (False, True)


def _spore_wall_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    """The microsporidiadb spore wall counts: three fields, and the site default."""
    if json.loads(wire(params, "text_fields")) == json.loads(_ALL_FIELDS):
        return recorded_count("report_text_spore_wall_all_fields")
    return recorded_count("report_text_spore_wall_three_fields")


@pytest.mark.asyncio
async def test_a_chosen_subset_of_fields_is_counted_at_the_site_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _spore_wall_count)
    params: dict[str, ParamValue] = {
        "text_search_organism": MultiPickValue(values=[_E_CUNICULI]),
        "text_expression": StringValue(value='"spore wall"'),
        "document_type": StringValue(value="gene"),
        "text_fields": MultiPickValue(values=["product", "Products", "Notes"]),
    }

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="microsporidiadb",
            record_type="transcript",
            search_name="GenesByText",
            params=params,
            count=recorded_count("report_text_spore_wall_three_fields"),
        ),
        values=_bound(params, {"text_fields": "chosen", "document_type": "default"}),
        infos=_sheet(_TEXT),
    )

    assert measured == [
        Measurement(
            kind="site_default",
            param="text_fields",
            count=10,
            reading="all 26 options",
        ),
        Measurement(
            kind="options_not_taken",
            param="text_fields",
            unchosen=_FIELDS_NOT_TAKEN,
            unchosen_count=23,
        ),
    ]
    assert recorded_count("report_text_spore_wall_three_fields") == 2


def _percentile_params() -> dict[str, ParamValue]:
    return {
        "min_expression_percentile": StringValue(value="80"),
        "channel": SinglePickValue(value="Channel 1"),
    }


@pytest.mark.asyncio
async def test_a_binding_whose_count_did_not_arrive_records_each_value_unmeasured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, lambda _s, _p: None)
    params = _percentile_params()

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByRNASeqPercentile",
            params=params,
            count=None,
        ),
        values=_bound(
            params, {"min_expression_percentile": "default", "channel": "default"}
        ),
        infos=_sheet(_PCT),
    )

    assert (asked, measured) == (
        [],
        [
            Measurement(
                kind="bound_count", param="min_expression_percentile", reading="80"
            ),
            Measurement(kind="bound_count", param="channel", reading="Channel 1"),
        ],
    )


def _ortholog_params() -> dict[str, ParamValue]:
    return {
        "organism": MultiPickValue(values=[CRYPTO_IOWA]),
        "included_species": StringValue(value=", ".join(TGON_STRAINS)),
        "excluded_species": StringValue(value="hsap"),
        "profile_pattern": StringValue(
            value="%hsap:N%" + "".join(f"{c}:Y%" for c in TGON_STRAINS)
        ),
    }


def _no_exclusion(_search: str, params: Mapping[str, ParamValue]) -> int:
    assert wire(params, "profile_pattern") == "%" + "".join(
        f"{c}:Y%" for c in TGON_STRAINS
    )
    return recorded_count("report_ortholog_tgon_no_exclusion")


@pytest.mark.asyncio
async def test_a_chosen_excluded_species_is_counted_with_none_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _no_exclusion)
    params = _ortholog_params()

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="cryptodb",
            record_type="transcript",
            search_name="GenesByOrthologPattern",
            params=params,
            count=recorded_count("report_ortholog_tgon_all"),
        ),
        values=_bound(params, {"excluded_species": "chosen"}),
        infos=_sheet(_ORTHOLOG),
        tree=phyletic_tree_of(list(_ORTHOLOG.parameters or [])),
    )

    assert measured == [
        Measurement(
            kind="loosest_bound",
            param="excluded_species",
            count=2408,
            reading="no species excluded",
        )
    ]


def test_each_phyletic_code_is_labelled_by_its_organism() -> None:
    params: dict[str, ParamValue] = {
        "included_species": StringValue(value="tgma, tggt"),
        "excluded_species": StringValue(value="hsap"),
        "profile_pattern": StringValue(value="%hsap:N%tggt:Y%tgma:Y%"),
    }

    labels = vocabulary_labels(_bound(params, {}), _sheet(_ORTHOLOG))

    assert [(m.param, m.reading, m.label) for m in labels.labels] == [
        ("included_species", "tgma", "Toxoplasma gondii MAS"),
        ("included_species", "tggt", "Toxoplasma gondii GT1"),
        ("excluded_species", "hsap", "Homo sapiens REF"),
        ("profile_pattern", "hsap", "Homo sapiens REF"),
        ("profile_pattern", "tggt", "Toxoplasma gondii GT1"),
        ("profile_pattern", "tgma", "Toxoplasma gondii MAS"),
    ]


@pytest.mark.asyncio
async def test_a_filter_is_counted_at_no_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
        seen.append(wire(params, "variation_sample_meta"))
        return 3

    serve_counts(monkeypatch, _count)
    params: dict[str, ParamValue] = {
        "variation_sample_meta": FilterValue.model_validate(
            {"filters": [{"field": "VAR_68bb04bd", "value": ["female"]}]}
        )
    }

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByNgsSnps",
            params=params,
            count=1,
        ),
        values=_bound(params, {"variation_sample_meta": "chosen"}),
        infos=_sheet(_SNPS),
    )

    assert (seen, measured) == (
        ['{"filters": []}'],
        [
            Measurement(
                kind="site_default",
                param="variation_sample_meta",
                count=3,
                reading="no filter",
            )
        ],
    )
