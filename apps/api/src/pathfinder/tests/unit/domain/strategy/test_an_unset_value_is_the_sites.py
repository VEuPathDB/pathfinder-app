"""A value that states nothing is the site's: a placeholder, the radio-off
value and the sheet default are unset, and a one-word pick at its default is
the site's unless the message names the parameter."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.value_source import is_unset, value_source
from pathfinder.tests._support.recorded_searches import client_search, suite_search

# The researcher's message of the schizont turn on plasmodb.
_ANY_DATASET = (
    "how many are expressed in the schizont stage in any P. knowlesi expression "
    "dataset? Go ahead and build that."
)
_ANY_OR_ALL = "Matches Any or All Selected Samples?"
_KNOWLESI = (
    "Plasmodium knowlesi strain H genes with a Plasmodium-specific domain that "
    "have no ortholog in Homo sapiens."
)


def _param(fixture: str, name: str) -> ParameterInfo:
    sheet = format_param_info_typed(suite_search(fixture).parameters or [])
    return next(info for info in sheet if info.name == name)


def _source(
    name: str,
    value: ParamValue,
    info: ParameterInfo,
    texts: list[str],
) -> str:
    return value_source(
        value,
        initial_display_value=info.default_value,
        request_texts=texts,
        info=info,
        display_name=info.display_name,
    )


def test_the_radio_off_value_is_unset_under_an_empty_sheet_default() -> None:
    accession = _param("search_genes_by_interpro_domain", "domain_accession")

    assert (
        accession.default_value,
        is_unset(StringValue(value="N/A"), accession.default_value, accession),
        is_unset(StringValue(value="PF05795"), accession.default_value, accession),
    ) == ("", True, False)


def test_a_site_placeholder_is_unset_whatever_it_names() -> None:
    sheet = format_param_info_typed(
        client_search("search_genes_by_location").parameters or []
    )
    sequence = next(info for info in sheet if info.name == "sequenceId")

    assert [
        is_unset(StringValue(value="(Example: chr22)"), "(Example: chr22)", sequence),
        is_unset(StringValue(value="(Example: Pf3D7_04_v3)"), "", sequence),
        is_unset(StringValue(value="n/a"), "", sequence),
        is_unset(StringValue(value="chr22"), "(Example: chr22)", sequence),
    ] == [True, True, True, False]


def test_a_term_the_vocabulary_offers_is_never_a_placeholder() -> None:
    """The parameter's own sheet decides a placeholder, not a text pattern."""
    status = ParameterInfo.model_validate(
        {
            "name": "status",
            "display_name": "Status",
            "type": "single-pick-vocabulary",
            "required": True,
            "is_visible": True,
            "help": "",
            "value_format": "",
            "default_value": "",
            "allowed_values": [{"value": "N/A", "display": "not applicable"}],
        }
    )

    assert is_unset(SinglePickValue(value="N/A"), "", status) is False
    assert _source("status", SinglePickValue(value="N/A"), status, []) == "chosen"


def test_a_value_at_the_sheet_default_is_unset() -> None:
    any_or_all = _param("search_genes_by_rnaseq_gomez_diaz_percentile", "any_or_all")

    assert (
        is_unset(SinglePickValue(value="any"), any_or_all.default_value, any_or_all),
        is_unset(SinglePickValue(value="all"), any_or_all.default_value, any_or_all),
    ) == (True, False)


def test_the_radio_off_value_is_the_sites_even_under_an_empty_default() -> None:
    accession = _param("search_genes_by_interpro_domain", "domain_accession")

    assert (
        _source("domain_accession", StringValue(value="N/A"), accession, ["N/A"])
        == "default"
    )


def test_a_one_word_pick_at_its_default_is_the_sites_when_the_message_names_no_parameter() -> (
    None
):
    any_or_all = _param("search_genes_by_rnaseq_gomez_diaz_percentile", "any_or_all")

    assert (
        any_or_all.display_name,
        _source("any_or_all", SinglePickValue(value="any"), any_or_all, [_ANY_DATASET]),
    ) == (_ANY_OR_ALL, "default")


def test_a_one_word_pick_the_message_writes_beside_the_parameter_is_stated() -> None:
    any_or_all = _param("search_genes_by_rnaseq_gomez_diaz_percentile", "any_or_all")

    assert [
        _source("any_or_all", SinglePickValue(value="any"), any_or_all, [text])
        for text in (
            "expressed above 80 in any selected sample",
            "keep genes expressed in any of the samples",
        )
    ] == ["stated", "stated"]


def test_a_one_word_pick_off_its_default_the_message_writes_is_stated() -> None:
    any_or_all = _param("search_genes_by_rnaseq_gomez_diaz_percentile", "any_or_all")

    assert (
        _source(
            "any_or_all",
            SinglePickValue(value="all"),
            any_or_all,
            ["genes above 80 in all samples"],
        )
        == "stated"
    )


def test_a_pick_of_several_words_at_its_default_the_message_holds_is_stated() -> None:
    organism = _param("search_genes_by_interpro_domain", "organism")

    assert (
        value_source(
            MultiPickValue(values=["Plasmodium knowlesi strain H"]),
            initial_display_value='["Plasmodium knowlesi strain H"]',
            request_texts=[_KNOWLESI],
            info=organism,
            display_name=organism.display_name,
        )
        == "stated"
    )
