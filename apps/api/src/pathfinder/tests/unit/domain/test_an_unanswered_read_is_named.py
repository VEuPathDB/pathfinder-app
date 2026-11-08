from __future__ import annotations

from pathfinder.domain.site_checks import (
    SiteCheck,
    unanswered_checks,
    unanswered_columns,
    unanswered_verdict,
)

_PASSED = SiteCheck(
    kind="step_valid",
    subject="the strategy on the site",
    status="pass",
    evidence="the site marks 1 of 1 step valid",
)


def test_a_strategy_read_the_site_did_not_answer_leaves_the_strategy_unchecked() -> (
    None
):
    checks = [*unanswered_checks("the site did not answer the strategy read"), _PASSED]

    assert unanswered_verdict(checks) == (
        "The site did not answer, so the strategy is not checked"
    )


def test_the_reads_the_site_did_not_answer_are_named_beside_the_passes() -> None:
    checks = [
        _PASSED,
        _PASSED,
        unanswered_columns("step 7"),
        unanswered_columns("step 8"),
    ]

    assert unanswered_verdict(checks) == (
        "2 checks passed; the site did not answer the column read of step 7; the site "
        "did not answer the column read of step 8, so those are not checked"
    )


def test_every_read_answered_gives_no_unanswered_verdict() -> None:
    assert [unanswered_verdict([_PASSED]), unanswered_verdict([])] == [None, None]
