from __future__ import annotations

import pytest

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    PercentileEnd,
    PercentileValue,
    is_blocking,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.domain.strategy._linked_values import linked, requirement

_MIN, _MAX = "min_percentile_chosen", "max_percentile_chosen"


def _grounded(
    end: PercentileEnd, share: float, values: dict[str, str], *params: str | None
) -> GroundedConstraint:
    held = requirement(ConstraintKind.PERCENTILE, PercentileValue(end=end, share=share))
    spec = OperationalSpec(goal="g", criteria=[linked(held, values, *params)])
    [grounded] = ground_against_spec([held], spec)
    return grounded


@pytest.mark.parametrize(
    ("end", "share", "values", "params", "realized"),
    [
        ("top", 5, {_MIN: "95"}, [_MIN], (_MIN, "95")),
        ("top", 99, {_MIN: "1", _MAX: "100"}, [_MIN, _MAX], (_MIN, "1")),
        ("bottom", 10, {_MIN: "0", _MAX: "10"}, [_MAX, _MIN], (_MAX, "10")),
    ],
)
def test_a_linked_bound_at_the_share_s_end_meets_it(
    end: PercentileEnd,
    share: float,
    values: dict[str, str],
    params: list[str],
    realized: tuple[str, str],
) -> None:
    grounded = _grounded(end, share, values, *params)

    assert (grounded.status, grounded.realized_param, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        *realized,
    )
    assert grounded_check(grounded).status == "pass"


def test_a_linked_bound_that_keeps_another_share_fails_its_check() -> None:
    grounded = _grounded("top", 10, {_MIN: "80"}, _MIN)

    assert (grounded.status, grounded.note, grounded_check(grounded).status) == (
        ConstraintStatus.SUBSTITUTED,
        "bound 80 means top 20%",
        "fail",
    )
    assert is_blocking(grounded)


def test_the_other_end_cut_short_of_the_full_scale_fails_its_check() -> None:
    grounded = _grounded("top", 10, {_MIN: "90", _MAX: "95"}, _MIN, _MAX)

    assert (grounded.status, grounded.realized_param, grounded.note) == (
        ConstraintStatus.SUBSTITUTED,
        _MAX,
        "bound 95 cuts the top 10% at its other end",
    )


@pytest.mark.parametrize(
    ("values", "params", "why"),
    [
        ({_MIN: "90"}, [], "no criterion links it to a parameter"),
        ({_MIN: "90"}, [None], "no criterion links it to a parameter"),
        ({_MAX: "100"}, [_MAX], "no linked parameter holds the top end"),
        ({"samples": "all"}, ["samples"], "no linked parameter holds the top end"),
    ],
)
def test_a_share_no_link_bounds_is_not_verified_and_never_blocks(
    values: dict[str, str], params: list[str | None], why: str
) -> None:
    grounded = _grounded("top", 10, values, *params)

    check = grounded_check(grounded)
    assert (grounded.status, grounded.realized_value, grounded.note) == (
        ConstraintStatus.GROUNDED,
        None,
        why,
    )
    assert (check.status, is_blocking(grounded)) == ("unchecked", False)


def test_a_percentile_held_with_no_value_is_not_verified() -> None:
    held = requirement(ConstraintKind.PERCENTILE, None, "top 10 percent")
    spec = OperationalSpec(goal="g", criteria=[linked(held, {_MIN: "90"}, _MIN)])

    [grounded] = ground_against_spec([held], spec)

    assert (grounded.status, grounded.note, grounded_check(grounded).status) == (
        ConstraintStatus.GROUNDED,
        "no typed value to compare",
        "unchecked",
    )
