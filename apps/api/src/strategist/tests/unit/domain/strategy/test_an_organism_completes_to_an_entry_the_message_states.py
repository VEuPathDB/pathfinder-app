from __future__ import annotations

import pytest

from strategist.domain.strategy.organism_phrases import (
    completed_entry,
    stated_organisms,
)
from strategist.tests._support.site_organisms import recorded_organisms

PEST = (
    "Find Anopheles gambiae PEST genes with a predicted signal peptide and 2 to 99 "
    "transmembrane domains."
)
NEOSPORA = "Carry these to their orthologs in Neospora caninum Liverpool."
IOWA = "Find Cryptosporidium parvum Iowa II genes with a signal peptide"
TWO_STRAINS = (
    "Find genes that differ between Plasmodium falciparum 3D7 and "
    "Plasmodium falciparum HB3"
)


def test_the_strain_is_part_of_the_entry_the_message_states() -> None:
    [stated] = stated_organisms(PEST, recorded_organisms("vectorbase"))

    assert stated.entry == "Anopheles gambiae PEST"
    assert (stated.start, stated.end) == (1, 4)


def test_the_longest_entry_at_a_position_wins() -> None:
    message = "Find Neospora caninum Liverpool 2019 genes"

    [stated] = stated_organisms(message, recorded_organisms("toxodb"))

    assert stated.entry == "Neospora caninum Liverpool 2019"


def test_a_genus_written_as_an_initial_states_the_entry() -> None:
    message = "Find P. falciparum 3D7 genes with a signal peptide"

    [stated] = stated_organisms(message, recorded_organisms("plasmodb"))

    assert stated.entry == "Plasmodium falciparum 3D7"


def test_a_species_without_its_strain_states_no_entry() -> None:
    message = "Find Plasmodium falciparum genes with a signal peptide"

    assert stated_organisms(message, recorded_organisms("plasmodb")) == []


@pytest.mark.parametrize(
    ("site", "words", "message", "entry"),
    [
        ("vectorbase", "Anopheles gambiae", PEST, "Anopheles gambiae PEST"),
        ("toxodb", "Neospora caninum", NEOSPORA, "Neospora caninum Liverpool"),
        ("cryptodb", "Cryptosporidium parvum", IOWA, "Cryptosporidium parvum Iowa II"),
        ("cryptodb", "C. parvum Iowa", IOWA, "Cryptosporidium parvum Iowa II"),
        (
            "plasmodb",
            "P. falciparum 3D7",
            "Find P. falciparum 3D7 genes",
            "Plasmodium falciparum 3D7",
        ),
        (
            "plasmodb",
            "Plasmodium falciparum HB3",
            TWO_STRAINS,
            "Plasmodium falciparum HB3",
        ),
    ],
)
def test_a_reading_that_begins_a_stated_entry_completes_to_it(
    site: str, words: str, message: str, entry: str
) -> None:
    assert completed_entry(words, message, recorded_organisms(site)) == entry


_UNSTATED = [
    ("Plasmodium falciparum", "Find Plasmodium falciparum genes"),
    ("Plasmodium falciparum", TWO_STRAINS),
    ("Plasmodium vivax", "Find Plasmodium falciparum 3D7 genes"),
    ("3D7", "How many protein-coding genes does 3D7 have?"),
    ("Plasmodium falciparum 3D7", "How many protein-coding genes does 3D7 have?"),
    ("Plasmodium vivax P01", "Find genes in vivax"),
]


def test_no_single_stated_entry_leaves_the_reading_without_one() -> None:
    organisms = recorded_organisms("plasmodb")

    completed = [completed_entry(w, m, organisms) for w, m in _UNSTATED]

    assert completed == [None] * len(_UNSTATED)
