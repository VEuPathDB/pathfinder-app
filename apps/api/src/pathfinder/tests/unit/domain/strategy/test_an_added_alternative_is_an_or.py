"""Only an "include" verb adds an alternative in words other than "or"; "in
addition to" and a trailing "as well" state neither operator, and a sentence
that adds a restriction states an AND."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.message_reading import (
    combination_operator_is_stated,
)
from pathfinder.domain.strategy.stated_requirements import attributed

_KINASES_OR_PHOSPHATASES = CombinationRequest(
    operator="OR", terms=["kinases", "phosphatases"]
)


@pytest.mark.parametrize(
    "message",
    [
        "Find kinases, and also include phosphatases.",
        "In addition to kinases, include phosphatases.",
        "Broaden the kinases to include phosphatases.",
        "Add phosphatases as an alternative to kinases.",
    ],
)
def test_an_added_alternative_joins_the_terms_with_or(message: str) -> None:
    assert (
        combination_operator_is_stated(message, _KINASES_OR_PHOSPHATASES),
        combination_operator_is_stated(
            message,
            CombinationRequest(operator="AND", terms=["kinases", "phosphatases"]),
        ),
    ) == (True, False)


def test_a_broadened_strategy_states_the_or_over_the_earlier_term() -> None:
    combination = Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value="kinases OR phosphatases",
        label="gene classes",
    )

    [recorded] = attributed(
        [combination],
        [
            "Broaden the strategy to include phosphatases.",
            "Plasmodium falciparum 3D7 kinases.",
        ],
        [],
    )

    assert (recorded.source, recorded.hard) == (ConstraintSource.USER_EXPLICIT, True)


def test_an_added_restriction_joins_the_terms_with_and() -> None:
    message = "Find kinases that also have a signal peptide."

    assert (
        combination_operator_is_stated(
            message,
            CombinationRequest(operator="AND", terms=["kinases", "signal peptide"]),
        ),
        combination_operator_is_stated(
            message,
            CombinationRequest(operator="OR", terms=["kinases", "signal peptide"]),
        ),
    ) == (True, False)


@pytest.mark.parametrize(
    ("message", "terms"),
    [
        ("Find kinases, and phosphatases as well.", ["kinases", "phosphatases"]),
        (
            (
                "Find P. falciparum 3D7 genes that have a signal peptide in "
                "addition to a GPI anchor."
            ),
            ["signal peptide", "GPI anchor"],
        ),
        (
            (
                "Find P. falciparum 3D7 genes that have a signal peptide and a "
                "GPI anchor as well."
            ),
            ["signal peptide", "GPI anchor"],
        ),
    ],
)
def test_in_addition_to_and_as_well_state_no_or(message: str, terms: list[str]) -> None:
    stated = [
        combination_operator_is_stated(
            message, CombinationRequest(operator=operator, terms=terms)
        )
        for operator in ("OR", "AND")
    ]

    assert stated == [False, False]


def test_an_or_added_in_addition_is_no_researchers_combination() -> None:
    combination = Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value="signal peptide OR GPI anchor",
        label="evidence",
    )

    [recorded] = attributed(
        [combination],
        ["Find genes that have a signal peptide in addition to a GPI anchor."],
        [],
    )

    assert (recorded.source, recorded.hard) == (ConstraintSource.ASSUMED, False)
