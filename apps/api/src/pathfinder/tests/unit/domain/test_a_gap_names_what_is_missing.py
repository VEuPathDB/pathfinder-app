"""A gap is what the strategy does not answer, typed by its source, and each
one is listed once with its sentence."""

from __future__ import annotations

from pathfinder.domain.caveats import RequirementGap, WordGap, check_gaps
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap, failed


def test_each_gap_is_listed_once_with_its_sentence() -> None:
    gaps = [
        *check_gaps(words=["exported"], unstated=["exported", "in the host cell"]),
        *failed(
            [
                SiteCheck(
                    kind="result_count",
                    subject="the strategy on the site",
                    status="fail",
                    evidence="the result step 7 ('Signal') holds no record on the site",
                ),
                SiteCheck(
                    kind="step_valid",
                    subject="the strategy on the site",
                    status="pass",
                    evidence="the site marks 2 of 2 steps valid",
                ),
            ]
        ),
    ]

    assert [gap.sentence for gap in gaps] == [
        "'exported': no search the strategy runs states it",
        "'in the host cell': no search on this site states it",
        (
            "'the strategy on the site': the result step 7 ('Signal') holds no "
            "record on the site"
        ),
    ]
    assert [type(gap) for gap in gaps] == [WordGap, RequirementGap, SiteCheckGap]
