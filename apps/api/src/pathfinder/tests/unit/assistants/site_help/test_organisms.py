"""The species a site's organism vocabulary names, and the strains under them.

The terms are the ones the live vocabularies carry, so a rule that invents a
species is visible here.
"""

from __future__ import annotations

from pathfinder.assistants.site_help.organisms import (
    OrganismSummary,
    organism_note,
    organism_summaries,
    organisms_of_genus,
)

# From plasmodb's own organism parameter.
_PLASMODB = [
    "Plasmodium falciparum 3D7",
    "Plasmodium falciparum Dd2",
    "Plasmodium berghei ANKA",
    "Haemoproteus tartakovskyi strain SISKIN1",
    "Hepatocystis sp. ex Piliocolobus tephrosceles 2019",
]
# From hostdb and cryptodb.
_HOSTDB = ["Homo sapiens REF", "Mus musculus"]
_CRYPTODB = [
    "Cryptosporidium parvum IOWA-ATCC",
    "Cryptosporidium sp. chipmunk LX-2015",
    "Cryptosporidium sp. 43IA8 isolate 43IA8",
]


def _by_species(terms: list[str]) -> dict[str, OrganismSummary]:
    return {summary.species: summary for summary in organism_summaries(terms)}


def test_a_species_carries_the_strains_the_site_lists_under_it() -> None:
    summaries = _by_species(_PLASMODB)

    assert summaries["Plasmodium falciparum"].strain_count == 2
    assert summaries["Plasmodium falciparum"].strains == ["3D7", "Dd2"]
    assert summaries["Haemoproteus tartakovskyi"].strains == ["strain SISKIN1"]


def test_an_organism_with_no_species_of_its_own_is_not_given_one() -> None:
    """`sp.` names an unclassified organism, so it is one entry, not a species."""
    summaries = _by_species(_CRYPTODB)

    assert "Cryptosporidium sp." not in summaries
    unclassified = summaries["Cryptosporidium sp. chipmunk LX-2015"]
    assert unclassified.strain_count == 0
    assert unclassified.strains == []


def test_a_like_epithet_names_an_organism_and_not_a_species() -> None:
    """The catalog files this term under `Plasmodium vivax-like sp.`."""
    summaries = _by_species(["Plasmodium vivax-like Pvl01"])

    assert "Plasmodium vivax-like" not in summaries
    assert summaries["Plasmodium vivax-like Pvl01"].strains == []


def test_an_organism_with_no_strain_qualifier_lists_no_strain() -> None:
    summaries = _by_species(_HOSTDB)

    assert summaries["Mus musculus"].strain_count == 0
    assert summaries["Mus musculus"].strains == []
    assert summaries["Homo sapiens"].strains == ["REF"]


def test_the_widest_species_come_first_and_the_rest_read_alphabetically() -> None:
    ordered = [summary.species for summary in organism_summaries(_PLASMODB)]

    assert ordered == [
        "Plasmodium falciparum",
        "Haemoproteus tartakovskyi",
        "Plasmodium berghei",
        "Hepatocystis sp. ex Piliocolobus tephrosceles 2019",
    ]


def test_a_genus_narrows_the_vocabulary_before_it_is_grouped() -> None:
    narrowed = organisms_of_genus(_PLASMODB, "plasmodium")

    assert narrowed == [
        "Plasmodium falciparum 3D7",
        "Plasmodium falciparum Dd2",
        "Plasmodium berghei ANKA",
    ]


def test_no_genus_keeps_every_organism() -> None:
    assert organisms_of_genus(_PLASMODB, "") == _PLASMODB


def test_the_note_names_what_the_listing_left_out() -> None:
    assert organism_note([], "") == ""
    note = organism_note([f"Aspergillus s{n}" for n in range(242)], "")
    assert "242 more species" in note
    assert "genus" in note


def test_the_note_for_one_genus_names_the_species_it_left_out() -> None:
    """A listing already narrowed to a genus cannot be narrowed again."""
    note = organism_note(["Aspergillus zonatus", "Aspergillus wentii"], "Aspergillus")
    assert note == (
        "2 more species of Aspergillus are not listed: "
        "Aspergillus zonatus, Aspergillus wentii."
    )
    assert "describe_site" not in note
