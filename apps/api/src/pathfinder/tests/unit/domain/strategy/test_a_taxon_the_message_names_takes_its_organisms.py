"""A pick of more than one organism is named by a taxon a message names whose
organisms are the pick's: a parent entry of the tree, or the genus its leaf
labels begin with."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.strategy.named_taxa import NamedTaxon, organism_trees
from pathfinder.tests._support.recorded_searches import suite_search

# The piroplasmadb organism tree holds Babesia under the family Babesiidae and
# under no genus entry, and Theileria under a genus entry of its own.
_TREE = organism_trees(suite_search("search_genes_by_taxon_piroplasmadb"))["organism"]
BABESIA_LEAVES = [
    "Babesia bigemina strain BOND",
    "Babesia bovis T2Bo",
    "Babesia caballi USDA-D6B2",
    "Babesia divergens strain 1802A",
    "Babesia duncani strain WA1 2023",
    "Babesia gibsoni Azabu",
    "Babesia microti strain RI",
    "Babesia ovata strain Miyake",
    "Babesia ovis Selcuk",
    "Babesia sp. Xinjiang Xinjiang",
]
_BABESIA_SPECIES = [
    "Babesia bigemina",
    "Babesia bovis",
    "Babesia caballi",
    "Babesia divergens",
    "Babesia duncani",
    "Babesia gibsoni",
    "Babesia microti",
    "Babesia ovata",
    "Babesia ovis",
    "Babesia sp. Xinjiang",
]
_THEILERIA = [
    "Theileria annulata strain Ankara",
    "Theileria equi strain WA",
    "Theileria orientalis Fish Creek",
    "Theileria orientalis Goon Nure",
    "Theileria orientalis strain Shintoku",
    "Theileria parva strain Muguga",
]
ACROSS_BABESIA = "Genes across Babesia with the GO term 'protein glycosylation'"
_GENUS = (NamedTaxon(name="Babesia", organisms=10), "Babesia")


def test_a_genus_the_message_names_takes_every_leaf_its_labels_begin_with() -> None:
    assert _TREE.named(BABESIA_LEAVES, [ACROSS_BABESIA]) == _GENUS


def test_the_species_entries_beside_their_leaves_take_the_same_organisms() -> None:
    assert _TREE.named([*_BABESIA_SPECIES, *BABESIA_LEAVES], [ACROSS_BABESIA]) == _GENUS


def test_a_parent_entry_takes_the_leaves_under_it() -> None:
    assert _TREE.named(["Babesiidae"], [ACROSS_BABESIA]) == _GENUS


def test_a_parent_entry_the_message_names_by_its_label_is_that_taxon() -> None:
    assert _TREE.named(_THEILERIA, ["theileria genes with a signal peptide"]) == (
        NamedTaxon(name="Theileria", organisms=6),
        "theileria",
    )


def test_a_genus_written_as_the_start_of_a_species_names_no_taxon() -> None:
    said = "Babesia bovis and Babesia microti genes with a signal peptide"

    assert [_TREE.named(BABESIA_LEAVES, [m]) for m in (said, ACROSS_BABESIA)] == [
        None,
        _GENUS,
    ]


def test_a_pick_of_part_of_the_genus_names_no_taxon() -> None:
    picks = (BABESIA_LEAVES[:9], BABESIA_LEAVES)

    assert [_TREE.named(p, [ACROSS_BABESIA]) for p in picks] == [None, _GENUS]


def test_a_genus_of_one_organism_names_no_taxon() -> None:
    said = "Cytauxzoon and Theileria genes with a signal peptide"
    picks = (["Cytauxzoon felis strain Winnie"], _THEILERIA)

    assert [_TREE.named(p, [said]) for p in picks] == [
        None,
        (NamedTaxon(name="Theileria", organisms=6), "Theileria"),
    ]


def test_the_taxon_shows_its_organism_count() -> None:
    assert NamedTaxon(name="Babesia", organisms=10).label() == "10 organisms"


def test_a_taxon_of_one_organism_is_refused() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        NamedTaxon(name="Cytauxzoon", organisms=1)
