"""A dependent pick keeps the label of the vocabulary it was bound under when it
is read again on the published sheet, and its vocabulary is read again only
when a parent holds a value other than the published one."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.value_binding import (
    bind_values,
    parents_moved,
    read_again,
)
from pathfinder.tests._support.recorded_searches import suite_search

# plasmodb GenesByInterproDomain: the published sheet under its default
# organism, and the sheet under Plasmodium falciparum 3D7 and Pfam.
_PUBLISHED = format_param_info_typed(
    suite_search("search_genes_by_interpro_domain").parameters or []
)
_UNDER_PF3D7 = format_param_info_typed(
    suite_search("search_genes_by_interpro_domain_under_pf3d7_pfam").parameters or []
)
_KH: dict[str, ParamValue] = {"domain_typeahead": MultiPickValue(values=["PF00013"])}


def test_the_published_sheet_alone_holds_no_label_for_the_domain() -> None:
    assert bind_values(_KH, "held", _PUBLISHED)["domain_typeahead"].label == ""


def test_the_bind_labels_the_domain_under_its_bound_parents() -> None:
    bound = bind_values(_KH, "stated", _UNDER_PF3D7)

    assert bound["domain_typeahead"].label == "KH domain"


def test_a_read_on_the_published_sheet_keeps_the_label_it_was_bound_under() -> None:
    bound = bind_values(_KH, "stated", _UNDER_PF3D7)

    again = read_again(bound, _PUBLISHED)

    assert again["domain_typeahead"].label == "KH domain"
    assert again["domain_typeahead"].source == "stated"


def test_a_pick_under_another_organism_needs_its_parents_read() -> None:
    values = {**_KH, "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])}

    assert parents_moved(values, ["domain_typeahead"], _PUBLISHED) is True


def test_a_pick_under_the_published_organism_reads_the_published_sheet() -> None:
    values = {
        **_KH,
        "organism": MultiPickValue(
            values=["Haemoproteidae", "Haemoproteus tartakovskyi strain SISKIN1"]
        ),
    }

    assert parents_moved(values, ["domain_typeahead"], _PUBLISHED) is False


def test_a_value_with_no_dependent_vocabulary_needs_no_parents_read() -> None:
    values: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
        "domain_accession": StringValue(value="PF00013"),
    }

    assert parents_moved(values, ["domain_accession"], _PUBLISHED) is False
