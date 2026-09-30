"""Each measurement of a bound value, read live, returns the counts the site
answered when the fixtures were recorded, and the label its vocabulary holds."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.wdk import phyletic_tree_of
from veupathdb_mcp.catalog import format_param_info_typed, read_search_definition

from pathfinder.domain.strategy.operational_spec import BoundValue, ValueSource
from pathfinder.services.strategies.measurements import (
    MEASUREMENT_BUDGET_SECONDS,
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.services.strategies.value_labels import vocabulary_labels
from pathfinder.tests._support.recorded_counts import (
    CRYPTO_IOWA,
    GIARDIA_WB,
    PERCENTILE_SEARCH,
    TGON_STRAINS,
    recorded_count,
    recorded_site_search,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_PROFILESET = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)


@pytest.fixture(autouse=True)
def registered(require_wdk_creds: str) -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def _bound(
    params: dict[str, ParamValue], measured: str, source: ValueSource
) -> dict[str, BoundValue]:
    return {
        name: BoundValue(value=value, source=source if name == measured else "stated")
        for name, value in params.items()
    }


async def _measured(
    site_id: str,
    search_name: str,
    params: dict[str, ParamValue],
    measured: str,
    organism_param: str | None = None,
) -> tuple[int | None, list[tuple[str, int | None, str]]]:
    """The bound count, then each measurement as kind, count and reading."""
    definition = await read_search_definition(site_id, "transcript", search_name)
    counts = TurnCounts()
    count = await counts.count(
        site_id,
        "transcript",
        search_name,
        params,
        timeout_seconds=MEASUREMENT_BUDGET_SECONDS,
    )
    assert count is not None
    found = await measure_binding(
        counts,
        MeasuredBinding(
            site_id=site_id,
            record_type="transcript",
            search_name=search_name,
            params=params,
            count=count,
            organism_param=organism_param,
        ),
        values=_bound(params, measured, "default"),
        infos=format_param_info_typed(list(definition.parameters or [])),
        tree=phyletic_tree_of(list(definition.parameters or [])),
    )
    return count, [(m.kind, m.count, m.reading) for m in found]


def _percentile() -> dict[str, ParamValue]:
    return {
        "profileset_generic": SinglePickValue(value=_PROFILESET),
        "samples_percentile_generic": MultiPickValue(values=["asexual blood stages"]),
        "min_expression_percentile": StringValue(value="80"),
        "max_expression_percentile": StringValue(value="100"),
        "any_or_all": SinglePickValue(value="any"),
        "protein_coding_only": SinglePickValue(value="yes"),
        "channel": SinglePickValue(value="Channel 1"),
    }


async def test_the_default_percentile_is_counted_at_zero() -> None:
    measured = await _measured(
        "plasmodb", PERCENTILE_SEARCH, _percentile(), "min_expression_percentile"
    )

    assert measured == (
        recorded_count("report_percentile_min_80"),
        [("loosest_bound", recorded_count("report_percentile_min_0"), "0")],
    )


async def test_a_quoted_word_is_counted_as_a_wildcard_and_in_site_search() -> None:
    params: dict[str, ParamValue] = {
        "text_expression": StringValue(value='"VSP"'),
        "text_search_organism": MultiPickValue(values=[GIARDIA_WB]),
        "document_type": StringValue(value="gene"),
        "text_fields": MultiPickValue(values=["product"]),
    }
    reach = next(
        kind.count
        for kind in recorded_site_search("site_search_vsp").document_types
        if kind.wdk_search_name == "GenesByText"
    )

    measured = await _measured(
        "giardiadb", "GenesByText", params, "text_expression", "text_search_organism"
    )

    assert measured == (
        recorded_count("report_text_vsp_quoted"),
        [
            ("site_search_reach", reach, '"VSP"'),
            ("wildcard_phrase", recorded_count("report_text_vsp_wildcard"), "VSP*"),
        ],
    )


async def test_the_text_search_reads_no_wildcard_inside_quotes() -> None:
    """A quoted phrase counts the same with a wildcard on each word, so only a
    single word is measured in its wildcard form."""
    counts = TurnCounts()

    phrase, starred = [
        await counts.count(
            "giardiadb",
            "transcript",
            "GenesByText",
            {
                "text_expression": StringValue(value=text),
                "text_search_organism": MultiPickValue(values=[GIARDIA_WB]),
                "document_type": StringValue(value="gene"),
                "text_fields": MultiPickValue(values=["product"]),
            },
            timeout_seconds=MEASUREMENT_BUDGET_SECONDS,
        )
        for text in ('"surface protein"', '"surface* protein*"')
    ]

    assert phrase is not None
    assert (phrase, starred) == (phrase, phrase)


async def test_the_toxoplasma_strains_are_counted_both_ways() -> None:
    pattern = "%" + "%".join(["hsap:N", *(f"{c}:Y" for c in TGON_STRAINS)]) + "%"
    params: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=[CRYPTO_IOWA]),
        "phyletic_indent_map": MultiPickValue(values=[]),
        "phyletic_term_map": MultiPickValue(values=[]),
        "included_species": StringValue(value=", ".join(TGON_STRAINS)),
        "excluded_species": StringValue(value="hsap"),
        "profile_pattern": StringValue(value=pattern),
    }
    anywhere = recorded_count("report_ortholog_tgon_omitted") - recorded_count(
        "report_ortholog_tgon_none"
    )

    measured = await _measured(
        "cryptodb", "GenesByOrthologPattern", params, "included_species"
    )

    assert measured == (
        recorded_count("report_ortholog_tgon_all"),
        [
            ("any_strain", anywhere, "at least one of 15 species"),
            (
                "all_strains",
                recorded_count("report_ortholog_tgon_all"),
                "all 15 species",
            ),
        ],
    )


async def test_each_pick_is_labelled_from_the_live_vocabulary() -> None:
    definition = await read_search_definition(
        "plasmodb", "transcript", PERCENTILE_SEARCH
    )

    labels = vocabulary_labels(
        _bound(_percentile(), "", "stated"),
        format_param_info_typed(list(definition.parameters or [])),
    )

    assert {m.param: m.label for m in labels.labels}["protein_coding_only"] == (
        "protein coding"
    )
    assert labels.unlabelled == []


async def test_a_default_comparison_is_a_choice_and_any_or_all_is_not() -> None:
    """The antisense comparison counts differently, so the default names it;
    with one sample, all counts as any, so any names nothing."""
    counted = [
        await _measured("plasmodb", PERCENTILE_SEARCH, _percentile(), name)
        for name in ("profileset_generic", "any_or_all")
    ]

    assert counted == [
        (
            recorded_count("report_percentile_min_80"),
            [("options_not_taken", None, "")],
        ),
        (recorded_count("report_percentile_min_80"), []),
    ]
    assert recorded_count("report_percentile_antisense") != recorded_count(
        "report_percentile_all_samples"
    )


async def test_a_default_gene_type_is_counted_at_every_type() -> None:
    params: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
        "geneType": MultiPickValue(values=["protein coding"]),
        "includePseudogenes": SinglePickValue(value="No"),
    }

    measured = await _measured("plasmodb", "GenesByGeneType", params, "geneType")

    assert measured == (
        recorded_count("report_gene_type_protein_coding"),
        [
            (
                "loosest_bound",
                recorded_count("report_gene_type_every_type"),
                "all 3 options",
            ),
            ("options_not_taken", None, ""),
        ],
    )


async def test_each_phyletic_code_is_labelled_and_counted_live() -> None:
    params: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
        "included_species": StringValue(value="pfal, pber"),
        "excluded_species": StringValue(value="hsap"),
        "profile_pattern": StringValue(value="%hsap:N%pber:Y%pfal:Y%"),
    }
    definition = await read_search_definition(
        "plasmodb", "transcript", "GenesByOrthologPattern"
    )

    labels = vocabulary_labels(
        _bound(params, "", "stated"),
        format_param_info_typed(list(definition.parameters or [])),
    )
    measured = await _measured(
        "plasmodb", "GenesByOrthologPattern", params, "excluded_species"
    )

    assert [
        (m.param, m.reading, m.label)
        for m in labels.labels
        if m.param in {"included_species", "excluded_species"}
    ] == [
        ("included_species", "pfal", "Plasmodium falciparum 3D7"),
        ("included_species", "pber", "Plasmodium berghei ANKA"),
        ("excluded_species", "hsap", "Homo sapiens REF"),
    ]
    assert measured == (
        recorded_count("report_ortholog_pfal_pber_without_human"),
        [
            (
                "loosest_bound",
                recorded_count("report_ortholog_pfal_pber_no_exclusion"),
                "no species excluded",
            )
        ],
    )
