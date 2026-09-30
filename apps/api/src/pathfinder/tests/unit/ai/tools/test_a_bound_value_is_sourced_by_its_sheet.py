"""A bound value is sourced by its sheet: a read-only value is the site's, the
radio-off value is the site's, and a one-word pick at its default is the site's
by its values and by its labels alike."""

from __future__ import annotations

from veupathdb.domain.parameters import ParamValue, SinglePickValue, StringValue
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.tools.standalone._frame_sources import (
    bound_values,
    stated_by_their_labels,
)
from pathfinder.domain.strategy.operational_spec import Measurement
from pathfinder.tests._support.recorded_searches import suite_search

# Researcher messages the values below are bound under.
_GPI = (
    "Use a text search for GPI anchor in the gene product descriptions as the "
    "stand-in and keep it OR with the signal peptide"
)
_ANY_DATASET = (
    "how many are expressed in the schizont stage in any P. knowlesi expression "
    "dataset? Go ahead and build that."
)
_KNOWLESI = (
    "Plasmodium knowlesi strain H genes with a Plasmodium-specific domain that "
    "have no ortholog in Homo sapiens."
)


def _sheet(fixture: str) -> list[ParameterInfo]:
    return format_param_info_typed(suite_search(fixture).parameters or [])


def _sources(
    values: dict[str, ParamValue],
    fixture: str,
    texts: list[str],
    site_supplied: set[str],
) -> dict[str, str]:
    bound = bound_values(
        values,
        infos=_sheet(fixture),
        site_supplied=site_supplied,
        request_texts=texts,
        reason="the model's reason",
    )
    return {name: held.source for name, held in bound.items()}


def test_a_read_only_value_a_message_word_matches_is_the_sites() -> None:
    assert _sources(
        {
            "text_expression": StringValue(value="GPI anchor"),
            "document_type": StringValue(value="gene"),
        },
        "search_genes_by_text",
        [_GPI],
        {"document_type"},
    ) == {"text_expression": "stated", "document_type": "default"}


def test_the_radio_off_value_and_an_empty_list_are_the_sites() -> None:
    assert _sources(
        {"domain_accession": StringValue(value="N/A")},
        "search_genes_by_interpro_domain",
        [_KNOWLESI],
        {"domain_accession"},
    ) | _sources(
        {"included_species": StringValue(value="n/a")},
        "search_genes_by_ortholog_pattern",
        [_KNOWLESI],
        set(),
    ) == {"domain_accession": "default", "included_species": "default"}


def test_a_one_word_pick_at_its_default_is_the_sites_by_its_label_too() -> None:
    infos = _sheet("search_genes_by_rnaseq_gomez_diaz_percentile")
    bound = bound_values(
        {"any_or_all": SinglePickValue(value="any")},
        infos=infos,
        site_supplied={"any_or_all"},
        request_texts=[_ANY_DATASET],
        reason="",
    )

    restated = stated_by_their_labels(
        bound,
        [
            Measurement(
                kind="vocabulary_label", param="any_or_all", label="any", reading="any"
            )
        ],
        infos,
        [_ANY_DATASET],
    )

    assert (bound["any_or_all"].source, restated["any_or_all"].source) == (
        "default",
        "default",
    )


def test_a_species_the_message_names_without_its_marker_is_stated() -> None:
    infos = _sheet("search_genes_by_ortholog_pattern")
    bound = bound_values(
        {
            "excluded_species": StringValue(value="hsap"),
            "profile_pattern": StringValue(value="%hsap:N%"),
        },
        infos=infos,
        site_supplied=set(),
        request_texts=[_KNOWLESI],
        reason="the model's reason",
    )

    restated = stated_by_their_labels(
        bound,
        [
            Measurement(
                kind="vocabulary_label",
                param=param,
                label="Homo sapiens REF",
                reading="hsap",
            )
            for param in ("excluded_species", "profile_pattern")
        ],
        infos,
        [_KNOWLESI],
    )

    assert {n: (b.source, b.basis) for n, b in restated.items()} == {
        "excluded_species": ("stated", "Homo sapiens"),
        "profile_pattern": ("stated", "Homo sapiens"),
    }
