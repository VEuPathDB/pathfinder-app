"""Bound values for a test criterion, each with the source the test states."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from veupathdb.domain.parameters import ParamValue

from pathfinder.domain.strategy.operational_spec import BoundValue, ValueSource


def stated(value: ParamValue, basis: str = "") -> BoundValue:
    """One value the request states."""
    return BoundValue(value=value, source="stated", basis=basis)


def _source(
    name: str, defaulted: Collection[str], chosen: Mapping[str, str]
) -> ValueSource:
    if name in defaulted:
        return "default"
    if name in chosen:
        return "chosen"
    return "stated"


def bound(
    values: Mapping[str, ParamValue],
    *,
    defaulted: Collection[str] = (),
    chosen: Mapping[str, str] | None = None,
) -> dict[str, BoundValue]:
    """The values as a criterion binds them: stated, except the ``defaulted``
    names, which hold the site default, and the ``chosen`` ones, each with the
    reason the model gave."""
    reasons = chosen or {}
    return {
        name: BoundValue(
            value=value,
            source=_source(name, defaulted, reasons),
            basis=reasons.get(name, ""),
        )
        for name, value in values.items()
    }
