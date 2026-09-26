"""A word of the text is a qualifier only when it heads the compound its owning
parameter name heads. The names are the ones plasmodb published."""

from __future__ import annotations

import pytest

from pathfinder.ai.tools.standalone._qualifier_words import (
    qualifiers_of,
    the_one_search_naming,
)
from pathfinder.tests._support.recorded_searches import (
    toxodb_transcript_listing,
    transcript_listing,
)


def _qualifiers(text: str) -> list[str]:
    naming = the_one_search_naming(transcript_listing())
    return [
        q.word
        for q in qualifiers_of(text)
        if q.stem in naming and naming[q.stem].names(q)
    ]


@pytest.mark.parametrize(
    ("text", "word", "qualifies"),
    [
        ("predicted to be exported to the host cell", "cell", False),
        (
            "highest minor-allele frequency at most 5% across isolates",
            "isolates",
            False,
        ),
        ("do not vary much across P. falciparum isolates", "isolates", False),
        ("carry these to their syntenic orthologs", "syntenic", True),
        (
            "all Plasmodium falciparum 3D7 genes, pseudogenes included",
            "pseudogenes",
            True,
        ),
        ("genes with single-cell RNA-seq evidence", "cell", True),
        ("genes with single cell RNA-seq evidence", "cell", True),
        ("genes that do not vary much between 3D7 isolates", "isolates", True),
        (
            "exported to the host cell that have single-cell RNA-seq evidence",
            "cell",
            True,
        ),
        (
            "with single-cell RNA-seq evidence that are exported to the host cell",
            "cell",
            True,
        ),
    ],
)
def test_a_word_qualifies_when_its_modifier_reads_like_the_names(
    text: str, word: str, qualifies: bool
) -> None:
    assert (word in _qualifiers(text)) is qualifies


def test_the_owner_is_the_search_whose_parameter_names_carry_the_stem() -> None:
    naming = the_one_search_naming(transcript_listing())

    assert naming["cell"].search == "GenesBySingleCell"
    assert naming["cell"].modifiers == frozenset({"singl"})
    assert naming["isolat"].search == "GenesByNgsSnps"
    assert naming["isolat"].modifiers == frozenset({"percent"})
    assert naming["synten"].modifiers == frozenset({None})


def test_the_s10_wording_reads_no_qualifier_on_toxodb() -> None:
    naming = the_one_search_naming(toxodb_transcript_listing())
    text = (
        "predicted to be exported to the host cell, with an ExportPred score of "
        "at least 10"
    )

    assert naming["cell"].search == "GenesBySingleCell"
    assert [
        q.word
        for q in qualifiers_of(text)
        if q.stem in naming and naming[q.stem].names(q)
    ] == []
