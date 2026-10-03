"""A count of a transcript strategy is read as named in genes or in transcripts,
the reading the eval's ``countsInGenes`` column takes."""

from __future__ import annotations

from pathfinder.ai.lead.reply_claims import counts_in_the_wrong_unit, counts_named_as
from pathfinder.domain.evidence import ColumnFit, ThresholdSides

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


def test_the_decimals_of_a_score_before_a_dataset_name_are_no_count() -> None:
    prose = (
        "(over changes in sense and antisense transcripts 0.55, B. bovis T2Bo "
        "Transcript Profiling 0.47, Genomic Location 0.39)"
    )

    assert counts_in_the_wrong_unit(prose, "transcript", {55, 47}) == []


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


def _percentile_fit(sides: list[ThresholdSides] | None = None) -> ColumnFit:
    return ColumnFit(
        criterion_id="c_trophozoite",
        criterion_text="expressed in trophozoites",
        wdk_step_id=441173200,
        column="min_percentile_chosen",
        display_name="Min %ile (Within Chosen Samples)",
        bound_value="80 to 100" if sides is None else "",
        counted_in="transcripts",
        total=569,
        fitting=569 if sides is None else 0,
        fitting_at_most=569 if sides is None else 0,
        sides=sides or [],
    )


def test_a_column_fit_row_counts_transcripts_and_is_not_flagged() -> None:
    row = _percentile_fit().sentence
    assert row == (
        "569 of 569 transcripts fit Min %ile (Within Chosen Samples) (80 to 100)"
    )

    assert counts_in_the_wrong_unit(row, "transcript", [569]) == []


def test_the_sides_of_a_column_fit_are_not_flagged() -> None:
    sides = [
        ThresholdSides(
            value="80", above=300, above_at_most=300, below=269, below_at_most=269
        )
    ]

    assert (
        counts_in_the_wrong_unit(_percentile_fit(sides).sentence, "transcript", [569])
        == []
    )


def test_a_step_count_in_transcripts_beside_a_column_fit_row_is_flagged() -> None:
    shown = f"{_percentile_fit().sentence}\nThe strategy returns 569 transcripts."

    assert counts_in_the_wrong_unit(shown, "transcript", [569]) == [569]
