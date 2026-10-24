"""The words a range or a filter value reads as, in place of its JSON wire text."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter


class Bounds(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    min: float | str | None = None
    max: float | str | None = None


_CLAUSE_VALUE: TypeAdapter[Bounds | list[float | str]] = TypeAdapter(
    Bounds | list[float | str]
)


def _bound_text(bound: float | str) -> str:
    match bound:
        case float() if bound.is_integer():
            return str(int(bound))
        case _:
            return str(bound)


def bounds_text(bounds: Bounds) -> str:
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


def range_text(wire: str) -> str:
    return bounds_text(Bounds.model_validate_json(wire))


def clause_text(field: str, value: JsonValue, *, unknown: bool) -> str:
    match _CLAUSE_VALUE.validate_python(value):
        case Bounds() as bounds:
            shown = bounds_text(bounds)
        case terms:
            shown = ", ".join(_bound_text(term) for term in terms) or "none"
    return f"{field}: {shown} or unknown" if unknown else f"{field}: {shown}"


def filter_text(clauses: Sequence[str]) -> str:
    return "; ".join(clauses) or "no filter"


__all__ = ["Bounds", "bounds_text", "clause_text", "filter_text", "range_text"]
