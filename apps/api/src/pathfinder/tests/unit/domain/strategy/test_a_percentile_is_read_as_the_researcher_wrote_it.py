"""A percentile request reads as a share or as the percentile itself: "top 5
percent" and "95th percentile" both bound the percentile at 95."""

from __future__ import annotations

from pathfinder.domain.strategy.constraint_grounding import ground_constraints
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    PercentileRequest,
)
from pathfinder.domain.strategy.realized_spec import RealizedSpec

_TIGHTEN = "tighten it to the 95th percentile and tell me how the final count changes?"


def _read(text: str) -> tuple[str, float, float] | None:
    request = PercentileRequest.parse(text)
    return (
        None if request is None else (request.direction, request.share, request.bound)
    )


def test_an_ordinal_percentile_is_the_bound_it_names() -> None:
    assert [
        _read(_TIGHTEN),
        _read("95th percentile Minimum expression percentile"),
        _read("80th percentile or above"),
        _read("top 5 percent"),
        _read("below the 10th percentile"),
    ] == [
        ("top", 5.0, 95.0),
        ("top", 5.0, 95.0),
        ("top", 20.0, 80.0),
        ("top", 5.0, 95.0),
        ("bottom", 10.0, 10.0),
    ]


def test_a_percentile_named_with_its_end_is_the_bound_it_names() -> None:
    assert [
        _read("minimum expression percentile 1"),
        _read("at least the 90th percentile"),
        _read("percentile 75 or above"),
        _read("80 or higher expression percentile"),
        _read("maximum expression percentile 20"),
        _read("percentile 30 or below"),
        _read("90 minimum schizont expression percentile"),
    ] == [
        ("top", 99.0, 1.0),
        ("top", 10.0, 90.0),
        ("top", 25.0, 75.0),
        ("top", 20.0, 80.0),
        ("bottom", 20.0, 20.0),
        ("bottom", 30.0, 30.0),
        ("top", 10.0, 90.0),
    ]


def test_a_percentile_with_no_end_is_still_unread() -> None:
    assert [_read("expression percentile 40")] == [None]


def test_a_minimum_percentile_of_1_is_grounded_on_the_minimum_bound() -> None:
    [grounded] = ground_constraints(
        [
            Constraint(
                kind=ConstraintKind.PERCENTILE,
                requested_value="minimum expression percentile 1",
                label="expression percentile",
                source=ConstraintSource.USER_EXPLICIT,
            )
        ],
        RealizedSpec(
            search_names=["GenesByRNASeqPercentile"],
            param_names=frozenset({"min_percentile", "max_percentile"}),
            param_values={"min_percentile": "1", "max_percentile": "100"},
        ),
    )

    assert (grounded.status, grounded.realized_param) == (
        ConstraintStatus.GROUNDED,
        "min_percentile",
    )


def test_a_share_with_no_direction_is_still_unread() -> None:
    assert [_read("10%"), _read("the 10 percent")] == [None, None]


def test_a_stated_95th_percentile_is_grounded_on_the_minimum_percentile() -> None:
    [grounded] = ground_constraints(
        [
            Constraint(
                kind=ConstraintKind.PERCENTILE,
                requested_value="95th percentile",
                label="Minimum expression percentile",
                source=ConstraintSource.USER_EXPLICIT,
            )
        ],
        RealizedSpec(
            search_names=["GenesByRNASeqPercentile"],
            param_names=frozenset({"min_expression_percentile"}),
            param_values={"min_expression_percentile": "95"},
        ),
    )

    assert (grounded.status, grounded.realized_param) == (
        ConstraintStatus.GROUNDED,
        "min_expression_percentile",
    )
