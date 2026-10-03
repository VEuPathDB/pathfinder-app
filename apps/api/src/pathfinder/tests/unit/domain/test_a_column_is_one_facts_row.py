"""The facts show each column of a step once, whether the check measured it
short of the bound or read every record inside it."""

from __future__ import annotations

from pathfinder.domain.caveats import measured_caveats
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.tests._support.column_fits import TM_CRITERION, tm_fit


def _facts(*fits_read: int) -> TurnFacts:
    fits = [tm_fit(fitting, 40) for fitting in fits_read]
    return TurnFacts(
        caveats=measured_caveats(build=None, controls=[], column_fits=fits),
        column_fits=fits,
    )


def test_a_column_the_site_does_not_show_is_one_row() -> None:
    unshown = tm_fit(0, 0).model_copy(update={"shown": False, "total": 0})
    facts = TurnFacts(
        caveats=measured_caveats(build=None, controls=[], column_fits=[unshown]),
        column_fits=[unshown],
    )

    assert facts.lines() == [f"the site shows no column for '{TM_CRITERION}'"]


def test_a_column_short_of_the_bound_is_one_row() -> None:
    assert _facts(12).lines() == ["12 of 40 genes fit # TM Domains (2 to 99)"]


def test_a_column_read_twice_is_one_row() -> None:
    assert _facts(40, 40).lines() == ["40 of 40 genes fit # TM Domains (2 to 99)"]
