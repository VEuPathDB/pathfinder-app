"""A value binds on the scale its parameter names, from the researcher's words:
a fold written for a log2 parameter binds at its log2, and a log2 value shows
the fold it stands for."""

from __future__ import annotations

from pathfinder.domain.log2_scale import (
    fold_label,
    in_the_sites_scale,
    scale_of,
    stated_numbers,
    stated_on_the_other_scale,
    without_the_other_scale,
)

_LOG2 = "log2(Fold Change)"
_LOOSEN = "loosen the fold change to 1.5-fold"
_PLEASE_LOOSEN = "please loosen it to 1.5-fold"


def test_a_log2_value_shows_its_fold_change() -> None:
    assert (fold_label(_LOG2, "1.5"), fold_label(_LOG2, "0.585")) == (
        "2.83-fold",
        "1.5-fold",
    )


def test_a_parameter_on_another_scale_shows_no_fold() -> None:
    assert (
        fold_label("fold difference >=", "1.5"),
        fold_label("Log2 ratio", "high"),
    ) == (
        "",
        "",
    )


def test_a_display_name_names_its_scale() -> None:
    assert [
        scale_of(_LOG2),
        scale_of("fold difference >="),
        scale_of("Minimum expression percentile"),
    ] == ["log2", "fold", None]


def test_a_message_writes_a_fold_and_a_log2_number() -> None:
    assert [
        (s.number, s.scale, s.words)
        for s in stated_numbers(
            "a 1.5-fold cut, or log2 fold change 1, fold change of 3"
        )
    ] == [
        (1.5, "fold", "1.5-fold"),
        (1.0, "log2", "log2 fold change 1"),
        (3.0, "fold", "fold change of 3"),
    ]


def test_a_fold_the_researcher_wrote_binds_a_log2_parameter_at_its_log2() -> None:
    stated = [
        in_the_sites_scale(1.5, _LOG2, [text]) for text in (_LOOSEN, _PLEASE_LOOSEN)
    ]

    assert [(s.number, s.scale, s.words) for s in stated if s is not None] == [
        (1.5, "fold", "1.5-fold"),
        (1.5, "fold", "1.5-fold"),
    ]


def test_a_number_written_on_the_sites_scale_is_not_converted() -> None:
    assert (
        in_the_sites_scale(1.0, _LOG2, ["log2 fold change 1"]),
        in_the_sites_scale(2.0, "fold difference >=", ["at least 2-fold"]),
    ) == (None, None)


def test_a_log2_number_binds_a_fold_parameter_at_its_fold() -> None:
    stated = in_the_sites_scale(1.0, "fold difference >=", ["log2 fold change of 1"])

    assert stated is not None
    assert (stated.scale, stated.words) == ("log2", "log2 fold change of 1")


def test_the_log2_of_a_stated_fold_is_stated_by_the_fold() -> None:
    assert [
        stated_on_the_other_scale(0.585, _LOG2, [_LOOSEN]),
        stated_on_the_other_scale(1.5, _LOG2, [_LOOSEN]),
    ] == ["1.5-fold", ""]


def test_a_folds_number_is_blanked_for_a_log2_parameter() -> None:
    assert without_the_other_scale(_LOOSEN, _LOG2).split() == [
        "loosen",
        "the",
        "fold",
        "change",
        "to",
    ]


def test_a_fold_of_zero_is_no_fold_and_binds_nothing() -> None:
    assert (
        [s.number for s in stated_numbers("a 0-fold change, then 2-fold")],
        in_the_sites_scale(0, _LOG2, ["keep the 0-fold genes"]),
        stated_on_the_other_scale(1.0, _LOG2, ["keep the 0-fold genes"]),
    ) == ([2.0], None, "")


def test_a_parameter_that_names_neither_scale_takes_the_number_as_written() -> None:
    assert (
        in_the_sites_scale(1.5, "Minimum score", ["loosen it to 1.5-fold"]),
        stated_on_the_other_scale(1.5, "Minimum score", ["loosen it to 1.5-fold"]),
    ) == (None, "")
