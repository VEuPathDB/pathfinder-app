"""A value the request stated beside the value a step was built with."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict

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


class ConstraintCheck(CamelModel):
    """A value the request stated, compared with the value a step was built with."""

    model_config = ConfigDict(frozen=True)

    step_id: str = ""
    label: str
    requested: str
    realized: str
    honored: bool
    note: str = ""

    def shortfall(self) -> str:
        """The value asked beside the value the step was built at."""
        return f"{self.label} asked {self.requested}, built {self.realized}"


class CheckGap(CamelModel):
    """A value a study-step check computed short of the value the request stated."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["check"] = "check"
    check: ConstraintCheck

    @computed
    def sentence(self) -> str:
        """The check's shortfall, as a finding."""
        return f"Not met: {self.check.shortfall()}"

    def texts(self) -> list[str]:
        return [self.check.requested]

    def redacted(self, redact: Callable[[str], str]) -> CheckGap:
        held = self.check.model_copy(update={"requested": redact(self.check.requested)})
        return self.model_copy(update={"check": held})

    @property
    def fails_the_check(self) -> bool:
        return True


def shortfalls(checks: Sequence[ConstraintCheck]) -> list[CheckGap]:
    """A gap for each value a computed check found the step built short of."""
    return [CheckGap(check=check) for check in checks if not check.honored]


__all__ = ["CheckGap", "ConstraintCheck", "agrees", "shortfalls"]
