"""A column fit is the site's own column read over a whole step against the value
its criterion binds, and the sample caveat is worded from it alone."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.domain.caveats import SampleCaveat, measured_caveats, sample_caveat
from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.evidence import VerificationReview

_REFUSED = (
    "the site refused the # TM Domains (tm_count) column (HTTP 400) for "
    "'two or more transmembrane domains'"
)


def _fit(
    fitting: int,
    total: int,
    *,
    at_most: int | None = None,
    refused: int | None = None,
    no_value: int = 0,
) -> ColumnFit:
    return ColumnFit(
        criterion_id="c_tm",
        criterion_text="two or more transmembrane domains",
        wdk_step_id=441031663,
        column="tm_count",
        display_name="# TM Domains",
        bound_value="2 to 99",
        counted_in="transcripts",
        total=total,
        fitting=fitting,
        fitting_at_most=fitting if at_most is None else at_most,
        no_value=no_value,
        refused_status=refused,
    )


def test_every_gene_in_the_bound_fits_all() -> None:
    fit = _fit(840, 840)

    assert (fit.fits, fit.sentence) == (
        "all",
        "840 of 840 transcripts fit # TM Domains (2 to 99)",
    )


def test_a_bin_across_a_bound_is_stated_as_a_range_of_counts() -> None:
    fit = _fit(476, 840, at_most=618)

    assert (fit.fits, fit.sentence) == (
        "some",
        "476 to 618 of 840 transcripts fit # TM Domains (2 to 99)",
    )


def test_no_gene_in_the_bound_fits_none() -> None:
    assert _fit(0, 840).fits == "none"


def test_a_column_the_site_refuses_is_not_shown() -> None:
    fit = _fit(0, 0, refused=400)

    assert (fit.fits, fit.shown, fit.sentence) == ("not_shown", False, _REFUSED)


def test_records_with_no_value_are_stated_beside_the_fit() -> None:
    fit = _fit(740, 840, no_value=100)

    assert (fit.fits, fit.holds_no_value, fit.sentence) == (
        "some",
        False,
        "740 of 840 transcripts fit # TM Domains (2 to 99); 100 hold no value",
    )


def test_a_column_no_record_holds_a_value_of_is_stated_so() -> None:
    fit = _fit(0, 840, no_value=840)

    assert (fit.fits, fit.holds_no_value, fit.sentence) == (
        "none",
        True,
        "0 of 840 transcripts fit # TM Domains (2 to 99); 840 hold no value",
    )


def test_a_fit_and_its_records_with_no_value_fit_inside_the_step() -> None:
    assert _fit(800, 840, no_value=100).nesting_problem == (
        "a column fit holds fitting_at_most + no_value <= total"
    )


def test_the_counts_cannot_exceed_each_other() -> None:
    assert _fit(10, 8).nesting_problem == (
        "a column fit holds fitting <= fitting_at_most <= total"
    )


def test_a_refused_column_carries_no_count() -> None:
    assert _fit(3, 8, refused=400).nesting_problem == (
        "a column the site refused carries no count"
    )


def test_a_fit_that_does_not_nest_is_never_recorded() -> None:
    with pytest.raises(ValueError, match="fitting <= fitting_at_most <= total"):
        TurnMarkers().record_column_fits([_fit(10, 8)])


def test_only_a_fit_short_of_every_gene_is_a_sample_caveat() -> None:
    short = _fit(476, 840, at_most=618)

    assert [sample_caveat(_fit(840, 840)), sample_caveat(short)] == [
        None,
        SampleCaveat(fit=short),
    ]


def test_the_sample_caveat_is_worded_by_its_fit_and_never_unclear() -> None:
    caveats = measured_caveats(
        build=None,
        controls=[],
        column_fits=[_fit(840, 840), _fit(0, 0, refused=400), _fit(12, 40)],
    )

    assert [c.sentence for c in caveats] == [
        _REFUSED,
        "12 of 40 transcripts fit # TM Domains (2 to 99)",
    ]


def test_the_review_carries_the_fits_as_texts() -> None:
    review = VerificationReview(column_fits=[_fit(840, 840)])

    assert review.texts() == [
        "two or more transmembrane domains",
        "# TM Domains",
        "2 to 99",
    ]
