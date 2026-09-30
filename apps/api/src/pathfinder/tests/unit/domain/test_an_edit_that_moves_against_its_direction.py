"""An edit asked to loosen a step whose count fell, or to tighten one whose
count rose, is a caveat with both counts."""

from __future__ import annotations

from pathfinder.domain.caveats import EditDirectionCaveat, edit_direction_caveats

_STEP = "step_ae885aac"
_NAME = "Bradyzoite vs tachyzoite (DESeq)"


def test_a_loosened_step_whose_count_fell_is_a_caveat_with_both_counts() -> None:
    caveats = edit_direction_caveats(
        "loosen", {_STEP: 1535}, {_STEP: (_NAME, 1249)}, "gene"
    )

    assert caveats == [
        EditDirectionCaveat(
            step_id=_STEP,
            step_name=_NAME,
            direction="loosen",
            count_before=1535,
            count_after=1249,
        )
    ]
    assert caveats[0].sentence == (
        "'Bradyzoite vs tachyzoite (DESeq)' was edited to loosen it, and its "
        "count fell from 1,535 genes to 1,249 genes"
    )


def test_a_tightened_step_whose_count_rose_is_a_caveat() -> None:
    [caveat] = edit_direction_caveats(
        "tighten", {_STEP: 1249}, {_STEP: (_NAME, 1875)}, "gene"
    )

    assert caveat.sentence.endswith("its count rose from 1,249 genes to 1,875 genes")


def test_a_count_that_moved_the_asked_way_is_no_caveat() -> None:
    assert (
        edit_direction_caveats("loosen", {_STEP: 1249}, {_STEP: (_NAME, 1875)}, "gene"),
        edit_direction_caveats("other", {_STEP: 1535}, {_STEP: (_NAME, 1249)}, "gene"),
        edit_direction_caveats("loosen", {_STEP: 1535}, {_STEP: (_NAME, None)}, "gene"),
    ) == ([], [], [])
