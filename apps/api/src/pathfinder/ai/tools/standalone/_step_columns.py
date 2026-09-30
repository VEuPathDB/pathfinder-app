"""Which columns of a step's search may show the numeric values its criterion
binds, and how many records of the step hold a value inside those bounds."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import NumberValue, ParamValue
from veupathdb.wdk import (
    WDKAttributeField,
    WDKColumnDistribution,
    WDKParameter,
    WDKSearch,
)

from pathfinder.domain.evidence import ColumnFit, ThresholdSides
from pathfinder.domain.strategy.operational_spec import Criterion

# A column more than half the record type's searches carry, such as the
# search weight, does not describe one search.
_COMMON_SHARE = 2
_HISTOGRAM = "histogram"

type Side = Literal["at_least", "at_most"]


def bound_param_value(criterion: Criterion, name: str) -> ParamValue | None:
    """The value the criterion binds for one parameter, else None."""
    if name not in criterion.resolved_params:
        return None
    return criterion.resolved_params[name].value


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class Threshold:
    """One numeric value a search compares a column with; ``side`` is None when
    the site states no direction for it."""

    value: float
    wire: str
    side: Side | None = None


def _wire(value: float) -> str:
    return NumberValue(value=value).to_wire()


def _thresholds(parameter: WDKParameter, value: ParamValue) -> list[Threshold]:
    """A number range bounds each side it binds; a number is one threshold."""
    if parameter.type == "number-range" and value.type == "number-range":
        low, high = value.min, value.max
        return [
            *([Threshold(low, _wire(low), "at_least")] if low is not None else []),
            *([Threshold(high, _wire(high), "at_most")] if high is not None else []),
        ]
    if parameter.type == "number" and value.type == "number":
        return [Threshold(value.value, value.to_wire())]
    if parameter.type == "string" and parameter.is_number and value.type == "string":
        number = _number(value.value)
        return [] if number is None else [Threshold(number, value.value)]
    return []


@dataclass(frozen=True)
class ColumnBound:
    """One column of a search and the thresholds its criterion's values set."""

    column: str
    display_name: str
    thresholds: tuple[Threshold, ...]
    # The attribute histogram that reports a search's own column, else None;
    # a record type column is read with the byValue column reporter.
    histogram: str | None = None
    # The columns of the search that may show the bounds, this one included.
    rivals: int = 1


@dataclass(frozen=True)
class _Column:
    field: WDKAttributeField
    dynamic: bool

    def histogram(self) -> str | None:
        return next((f.name for f in self.field.formats if f.type == _HISTOGRAM), None)


def _columns(
    search: WDKSearch,
    record_attributes: Sequence[WDKAttributeField],
    searches: Sequence[WDKSearch],
) -> list[_Column]:
    """The search's own columns that the site reports a distribution of values for."""
    carried = Counter(
        name
        for each in searches
        for name in {
            *each.default_attributes,
            *(field.name for field in each.dynamic_attributes),
        }
    )
    by_name = {field.name: field for field in record_attributes}
    found = [
        *(_Column(field, dynamic=True) for field in search.dynamic_attributes),
        *(
            _Column(by_name[name], dynamic=False)
            for name in search.default_attributes
            if name in by_name
        ),
    ]
    return [
        c
        for c in found
        if c.histogram() is not None
        and carried[c.field.name] * _COMMON_SHARE <= len(searches)
    ]


def column_bounds(
    search: WDKSearch,
    parameters: Sequence[WDKParameter],
    record_attributes: Sequence[WDKAttributeField],
    searches: Sequence[WDKSearch],
    bound: Callable[[str], ParamValue | None],
) -> list[ColumnBound]:
    """The columns that may show the numeric values ``bound`` sets on the search.

    Every one of the search's own columns with a value distribution is a rival
    for every threshold; ``settled`` decides which fits stand.
    """
    thresholds = tuple(
        threshold
        for parameter in parameters
        if (value := bound(parameter.name)) is not None
        for threshold in _thresholds(parameter, value)
    )
    if not thresholds:
        return []
    columns = _columns(search, record_attributes, searches)
    return [
        ColumnBound(
            column=column.field.name,
            display_name=column.field.display_name or column.field.name,
            thresholds=thresholds,
            histogram=column.histogram() if column.dynamic else None,
            rivals=len(columns),
        )
        for column in columns
    ]


def settled(read: Sequence[tuple[ColumnBound, ColumnFit]]) -> list[ColumnFit]:
    """The fits that stand. A sole column's fit always stands; rival columns'
    fits stand only when every rival holds every record inside the bounds."""
    agreed = all(fit.fits == "all" for _, fit in read) and all(
        bound.rivals == len(read) for bound, _ in read
    )
    return [fit for bound, fit in read if bound.rivals == 1 or agreed]


@dataclass(frozen=True)
class ValueBin:
    """Records whose value lies in [start, end), or equals start when both agree."""

    start: str
    end: str
    count: int


class AttributeHistogram(BaseModel):
    """The attribute histogram reporter's answer: records by value."""

    model_config = ConfigDict(extra="ignore")

    data: dict[str, int] = {}

    def bins(self) -> list[ValueBin]:
        return [ValueBin(value, value, count) for value, count in self.data.items()]


def by_value_bins(distribution: WDKColumnDistribution) -> list[ValueBin]:
    """The byValue histogram, with the records that hold no value as one bin."""
    missing = distribution.statistics.num_missing_cases
    return [
        *(ValueBin(b.bin_start, b.bin_end, b.value) for b in distribution.histogram),
        *([ValueBin("", "", missing)] if missing else []),
    ]


@dataclass(frozen=True)
class _Interval:
    low: float = -math.inf
    high: float = math.inf

    def counts(self, bins: Sequence[ValueBin]) -> tuple[int, int]:
        """The records surely inside, and the most that may be inside."""
        if self.low > self.high:
            return 0, 0
        surely = possibly = 0
        for b in bins:
            whole, overlaps = self._holds(b)
            surely += b.count if whole else 0
            possibly += b.count if overlaps else 0
        return surely, possibly

    def _holds(self, b: ValueBin) -> tuple[bool, bool]:
        start, end = _number(b.start), _number(b.end)
        if start is None or end is None:
            return False, False
        if start == end:
            return (inside := self.low <= start <= self.high), inside
        whole = self.low <= start and end <= self.high
        return whole, end > self.low and start <= self.high


@dataclass(frozen=True)
class Measured:
    """The records inside the bounds whose side is known, and the records on
    each side of a threshold the step holds on neither side."""

    fitting: int
    fitting_at_most: int
    total: int
    bound_value: str
    sides: tuple[ThresholdSides, ...] = ()


def _held_side(
    threshold: Threshold, bins: Sequence[ValueBin], total: int
) -> Side | None:
    """The side of a threshold that holds every record, else None."""
    if _Interval(low=threshold.value).counts(bins)[0] == total:
        return "at_least"
    if _Interval(high=threshold.value).counts(bins)[0] == total:
        return "at_most"
    return None


def _both_sides(threshold: Threshold, bins: Sequence[ValueBin]) -> ThresholdSides:
    above = _Interval(low=threshold.value).counts(bins)
    below = _Interval(high=threshold.value).counts(bins)
    return ThresholdSides(
        value=threshold.wire,
        above=above[0],
        above_at_most=above[1],
        below=below[0],
        below_at_most=below[1],
    )


def _bound_value(low: Threshold | None, high: Threshold | None) -> str:
    match low, high:
        case Threshold(), Threshold():
            return f"{low.wire} to {high.wire}"
        case Threshold(), None:
            return f"{low.wire} or more"
        case None, Threshold():
            return f"{high.wire} or less"
        case _:
            return ""


def measured(bound: ColumnBound, bins: Sequence[ValueBin]) -> Measured:
    """The bounds read over one histogram: the known sides as one range, and
    every other threshold's count on each side."""
    total = sum(b.count for b in bins)
    known: list[Threshold] = []
    sides: list[ThresholdSides] = []
    for threshold in bound.thresholds:
        side = threshold.side or _held_side(threshold, bins, total)
        if side is None:
            sides.append(_both_sides(threshold, bins))
        else:
            known.append(replace(threshold, side=side))
    floors = [t for t in known if t.side == "at_least"]
    ceilings = [t for t in known if t.side == "at_most"]
    low = max(floors, key=lambda t: t.value, default=None)
    high = min(ceilings, key=lambda t: t.value, default=None)
    fitting, at_most = _Interval(
        low.value if low else -math.inf, high.value if high else math.inf
    ).counts(bins)
    return Measured(
        fitting=fitting,
        fitting_at_most=at_most,
        total=total,
        bound_value=_bound_value(low, high),
        sides=tuple(sides),
    )


__all__ = [
    "AttributeHistogram",
    "ColumnBound",
    "Measured",
    "Threshold",
    "ValueBin",
    "bound_param_value",
    "by_value_bins",
    "column_bounds",
    "measured",
    "settled",
]
