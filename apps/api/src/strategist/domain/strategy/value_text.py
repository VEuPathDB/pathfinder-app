"""The words a range or a filter value reads as, in place of its JSON wire text."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import (
    DateBounds,
    DateRange,
    FilterClause,
    MultiMembers,
    NumberBounds,
    NumberMembers,
    NumberRange,
    StringMembers,
)


class NumberEnds(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    min: float | None = None
    max: float | None = None


def _bound_text(bound: float | str) -> str:
    match bound:
        case float() if bound.is_integer():
            return str(int(bound))
        case _:
            return str(bound)


def bounds_text(bounds: NumberBounds | DateBounds) -> str:
    low = None if bounds.min is None else _bound_text(bounds.min)
    high = None if bounds.max is None else _bound_text(bounds.max)
    match low, high:
        case None, None:
            return "any"
        case _, None:
            return f"at least {low}"
        case None, _:
            return f"at most {high}"
        case _ if low == high:
            return f"{low}"
        case _:
            return f"{low} to {high}"


def clause_text(clause: FilterClause, name: str = "") -> str:
    match clause:
        case NumberRange(value=bounds) | DateRange(value=bounds):
            shown = bounds_text(bounds)
        case MultiMembers(value=multi):
            joined = " or " if multi.operation == "union" else " and "
            shown = joined.join(clause_text(leaf) for leaf in multi.filters)
        case StringMembers(value=terms) | NumberMembers(value=terms):
            shown = ", ".join(_bound_text(term) for term in terms) or "none"
    field = name or clause.field
    return (
        f"{field}: {shown} or unknown"
        if clause.include_unknown
        else f"{field}: {shown}"
    )


def filter_text(clauses: Sequence[str]) -> str:
    return "; ".join(clauses) or "no filter"


__all__ = ["NumberEnds", "bounds_text", "clause_text", "filter_text"]
