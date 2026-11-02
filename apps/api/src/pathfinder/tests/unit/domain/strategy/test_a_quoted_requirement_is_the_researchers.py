from __future__ import annotations

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.stated_requirements import attributed

_MESSAGE = (
    "Can you also require that they are expressed in trophozoites (minimum "
    "expression percentile 1)?"
)


def _percentile(quote: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.PERCENTILE,
        requested_value="expression percentile 1 and above",
        label="expression percentile 1 and above",
        quote=quote,
        source=ConstraintSource.USER_EXPLICIT,
    )


def test_a_rewritten_value_whose_quote_the_message_holds_is_stated() -> None:
    [held] = attributed([_percentile("minimum expression percentile 1")], [_MESSAGE])

    assert (held.source, held.hard) == (ConstraintSource.USER_EXPLICIT, True)


def test_a_rewritten_value_with_no_quote_the_message_holds_is_assumed() -> None:
    [held] = attributed([_percentile("")], [_MESSAGE])

    assert (held.source, held.hard) == (ConstraintSource.ASSUMED, False)


def test_a_value_the_message_words_with_no_quote_is_assumed() -> None:
    signal = Constraint(
        kind=ConstraintKind.OTHER,
        requested_value="signal peptide",
        label="signal peptide",
        source=ConstraintSource.USER_EXPLICIT,
    )

    [held] = attributed([signal], ["Find genes with a signal peptide."])

    assert (held.source, held.hard) == (ConstraintSource.ASSUMED, False)


def test_a_quote_an_earlier_message_holds_is_stated_in_any_case() -> None:
    [held] = attributed(
        [_percentile("MINIMUM expression percentile 1")],
        ["Keep it as it is.", _MESSAGE],
    )

    assert (held.source, held.hard) == (ConstraintSource.USER_EXPLICIT, True)
