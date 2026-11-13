"""Whether a value the request stated agrees with the value a step was built with."""

from __future__ import annotations

from collections.abc import Callable

# The most decimals a float written by a person or a site carries.
_MOST_DECIMALS = 15


def _decimals(value: float) -> int:
    """The fewest decimals that write the value exactly."""
    return next(
        (d for d in range(_MOST_DECIMALS) if round(value, d) == value),
        _MOST_DECIMALS,
    )


def _same(value: float) -> float:
    return value


def agrees(
    requested: float,
    bound: float,
    *,
    to_bound: Callable[[float], float] = _same,
    to_requested: Callable[[float], float] = _same,
) -> bool:
    """Whether each value, in the other's units, rounds to the other at the
    decimals that other is written with."""
    return (
        round(to_requested(bound), _decimals(requested)) == requested
        and round(to_bound(requested), _decimals(bound)) == bound
    )


__all__ = ["agrees"]
