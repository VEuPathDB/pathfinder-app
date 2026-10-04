"""A number PathFinder reads from a computation shows four significant
digits, its whole part in full, and no trailing zeros."""

from __future__ import annotations

from pathfinder.domain.strategy.number_precision import significant_number


def test_a_long_coordinate_shows_four_significant_digits() -> None:
    assert significant_number(79.3054615368446) == "79.31"
    assert significant_number(-17.0296652427709) == "-17.03"
    assert significant_number(0.443609763729234) == "0.4436"


def test_a_large_number_keeps_its_whole_part() -> None:
    assert significant_number(123456.789) == "123457"


def test_trailing_zeros_are_dropped() -> None:
    assert significant_number(-96.6031187877825) == "-96.6"
    assert significant_number(-11.0) == "-11"
    assert significant_number(0.0) == "0"


def test_a_small_number_keeps_four_significant_digits() -> None:
    assert significant_number(0.0000123456) == "0.00001235"
