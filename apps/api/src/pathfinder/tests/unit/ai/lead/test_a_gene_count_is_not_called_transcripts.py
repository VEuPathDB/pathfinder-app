"""A count of a transcript strategy is read as named in genes or in transcripts,
the reading the eval's ``countsInGenes`` column takes."""

from __future__ import annotations

from pathfinder.ai.lead.reply_claims import counts_in_the_wrong_unit, counts_named_as

_TRANSCRIPT_COUNT_REPLY = (
    "Their intersection contains **78 Toxoplasma gondii ME49 transcripts**, and "
    "the orthology search returns **145 transcripts**."
)
_HELD = (720, 946, 78, 145)


def test_a_transcript_count_the_strategy_holds_is_in_the_wrong_unit() -> None:
    assert counts_in_the_wrong_unit(_TRANSCRIPT_COUNT_REPLY, "transcript", _HELD) == [
        78,
        145,
    ]


def test_a_reply_that_counts_genes_is_in_the_site_s_unit() -> None:
    prose = _TRANSCRIPT_COUNT_REPLY.replace("transcripts", "genes")

    assert counts_in_the_wrong_unit(prose, "transcript", _HELD) == []


def test_a_transcript_count_the_strategy_does_not_hold_is_left_alone() -> None:
    prose = "The 145 genes come from 151 transcripts."

    assert counts_in_the_wrong_unit(prose, "transcript", _HELD) == []


def test_a_pathway_strategy_is_counted_in_pathways() -> None:
    assert counts_in_the_wrong_unit("It returns 145 pathways.", "pathway", _HELD) == []


def test_a_strain_name_between_the_count_and_the_noun_is_read_through() -> None:
    prose = "The strategy returns **479 Plasmodium falciparum 3D7 transcripts** here."

    assert counts_named_as(prose, "transcript", instead_of="gene") == [479]


def test_a_second_number_stands_for_its_own_count() -> None:
    prose = "It returned 52 of 80 transcripts."

    assert counts_named_as(prose, "transcript", instead_of="gene") == [80]
