from __future__ import annotations

import pytest
from veupathdb.domain.parameters import vocab_keys

from strategist.domain.strategy.organism_phrases import entry_holding
from strategist.tests._support.recorded_searches import suite_search
from strategist.tests._support.site_organisms import recorded_organisms


def _piroplasmadb() -> list[str]:
    taxon = suite_search("search_genes_by_taxon_piroplasmadb")
    [organism] = [p for p in taxon.parameters or [] if p.is_organism]
    return sorted(vocab_keys(organism.vocabulary))


def _vocabulary(site: str) -> list[str]:
    return _piroplasmadb() if site == "piroplasmadb" else recorded_organisms(site)


@pytest.mark.parametrize(
    ("site", "words", "message", "entry"),
    [
        (
            "tritrypdb",
            "Trypanosoma brucei TREU927",
            "Which Trypanosoma brucei TREU927 protein kinases have a signal peptide?",
            "Trypanosoma brucei brucei TREU927",
        ),
        (
            "tritrypdb",
            "T. brucei TREU927",
            "Kinases of T. brucei TREU927",
            "Trypanosoma brucei brucei TREU927",
        ),
        (
            "cryptodb",
            "Cryptosporidium meleagridis UKMEL1",
            "Find Cryptosporidium meleagridis UKMEL1 genes with a signal peptide",
            "Cryptosporidium meleagridis strain UKMEL1",
        ),
        (
            "piroplasmadb",
            "Cytauxzoon felis Winnie",
            "Which Cytauxzoon felis Winnie genes are kinases?",
            "Cytauxzoon felis strain Winnie",
        ),
    ],
)
def test_the_one_entry_that_holds_every_stated_word_in_order_is_named(
    site: str, words: str, message: str, entry: str
) -> None:
    assert entry_holding(words, message, _vocabulary(site)) == entry


_NOT_ONE = [
    (
        "tritrypdb",
        "Trypanosoma brucei Lister 427",
        "Kinases of Trypanosoma brucei Lister 427",
    ),
    ("tritrypdb", "Trypanosoma brucei", "Kinases of Trypanosoma brucei"),
    ("cryptodb", "Cryptosporidium meleagridis", "Cryptosporidium meleagridis genes"),
    ("plasmodb", "3D7", "Which genes of 3D7 have a signal peptide?"),
    ("plasmodb", "falciparum 3D7", "Which genes of falciparum 3D7 are kinases?"),
    ("plasmodb", "Plasmodium falciparum 3D7", "Which genes of P. vivax are kinases?"),
    ("plasmodb", "Plasmodium falciparum XX9", "Plasmodium falciparum XX9 genes"),
]


def test_words_held_by_no_entry_or_by_several_name_none() -> None:
    named = [entry_holding(w, m, _vocabulary(site)) for site, w, m in _NOT_ONE]

    assert named == [None] * len(_NOT_ONE)
