"""A column fit is the site's own column read over a whole step against the value
its criterion binds, and the sample caveat is worded from it alone."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.caveats import SampleCaveat, measured_caveats, sample_caveat
from pathfinder.domain.evidence import ColumnFit, VerificationReview


def _fit(
    fitting: int, total: int, *, at_most: int | None = None, shown: bool = True
) -> ColumnFit:
    return ColumnFit(
        criterion_id="c_tm",
        criterion_text="two or more transmembrane domains",
        wdk_step_id=441031663,
        column="tm_count",
        display_name="# TM Domains",
        bound_value="2 to 99",
        total=total,
        fitting=fitting,
        fitting_at_most=fitting if at_most is None else at_most,
        shown=shown,
    )


def test_every_gene_in_the_bound_fits_all() -> None:
    fit = _fit(840, 840)

    assert (fit.fits, fit.sentence) == (
        "all",
        "840 of 840 genes fit # TM Domains (2 to 99)",
    )


def test_a_bin_across_a_bound_is_stated_as_a_range_of_counts() -> None:
    fit = _fit(476, 840, at_most=618)

    assert (fit.fits, fit.sentence) == (
        "some",
        "476 to 618 of 840 genes fit # TM Domains (2 to 99)",
    )


def test_no_gene_in_the_bound_fits_none() -> None:
    assert _fit(0, 840).fits == "none"


def test_a_column_the_site_does_not_report_is_not_shown() -> None:
    fit = _fit(0, 0, shown=False)

    assert (fit.fits, fit.sentence) == (
        "not_shown",
        "the site shows no column for 'two or more transmembrane domains'",
    )


def test_the_counts_cannot_exceed_each_other() -> None:
    with pytest.raises(ValidationError, match="fitting <= fitting_at_most <= total"):
        _fit(10, 8)


def test_a_column_not_shown_carries_no_count() -> None:
    with pytest.raises(ValidationError, match="carries no count"):
        _fit(3, 8, shown=False)


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
        column_fits=[_fit(840, 840), _fit(0, 0, shown=False), _fit(12, 40)],
    )

    assert [c.sentence for c in caveats] == [
        "the site shows no column for 'two or more transmembrane domains'",
        "12 of 40 genes fit # TM Domains (2 to 99)",
    ]


def test_the_review_carries_the_fits_as_texts() -> None:
    review = VerificationReview(column_fits=[_fit(840, 840)])

    assert review.texts() == [
        "two or more transmembrane domains",
        "# TM Domains",
        "2 to 99",
    ]
