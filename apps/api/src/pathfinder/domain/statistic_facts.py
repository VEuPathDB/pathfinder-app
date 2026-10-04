"""The statistics the EDA service computed on a thread, which a reply's ``stat``
references render."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator, Sequence
from typing import Literal

from assistant_core.graph.tool_summary import count_noun
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.eda_parts import (
    EdaBoxplotBox,
    EdaPcaPart,
    EdaStatisticRow,
    EdaStatisticsPart,
)

type StatisticKind = Literal["pca", "two_by_two", "contingency", "boxplot", "trend"]

_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")


def statistic_id(kind: StatisticKind, variables: Sequence[str]) -> str:
    """The id of one statistic of these variables, the same on every read."""
    digest = hashlib.sha256("|".join([kind, *variables]).encode()).hexdigest()
    return f"stat_{digest[:8]}"


class StatisticRowFact(CamelModel):
    """One value of a statistic, under the name a reference gives it."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: str

    def numbers(self) -> list[str]:
        """Each number the value writes, without its digit separators."""
        return [found.replace(",", "") for found in _DIGITS.findall(self.value)]


class StatisticFact(CamelModel):
    """One statistic the service computed on the open analysis."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: StatisticKind
    title: str
    rows: list[StatisticRowFact] = Field(default_factory=list)

    def value(self, name: str) -> str | None:
        return next((row.value for row in self.rows if row.name == name), None)

    def lines(self) -> list[str]:
        return [self.title, *(f"{row.name}: {row.value}" for row in self.rows)]

    def redacted(self, redact: Callable[[str], str]) -> StatisticFact:
        return self.model_copy(update={"title": redact(self.title)})


def statistic_value(statistics: Sequence[StatisticFact], body: str) -> str | None:
    """The value a ``stat`` reference names as ``<id>.<row name>``."""
    held_id, _, name = body.partition(".")
    return next((s.value(name) for s in reversed(statistics) if s.id == held_id), None)


def statistic_references(
    statistics: Sequence[StatisticFact], number: str
) -> Iterator[str]:
    """Each ``stat`` reference whose value writes the number."""
    for statistic in statistics:
        for row in statistic.rows:
            if number in row.numbers():
                yield f"[stat:{statistic.id}.{row.name}]"


def pca_fact(part: EdaPcaPart) -> StatisticFact:
    """Each component's share of variance, and what the reduction plotted."""
    return StatisticFact(
        id=part.statistic_id,
        kind="pca",
        title=f"PCA of {part.sample_count} samples",
        rows=[
            *(
                StatisticRowFact(name=f"PC{index}", value=axis.stated_share)
                for index, axis in enumerate(part.axes, start=1)
            ),
            StatisticRowFact(
                name="samples", value=count_noun(part.sample_count, "sample")
            ),
            StatisticRowFact(
                name="groups", value=count_noun(part.group_count, "group")
            ),
        ],
    )


def _box_rows(box: EdaBoxplotBox) -> Iterator[StatisticRowFact]:
    for name, value in (
        ("lower fence", box.lower_fence),
        ("q1", box.q1),
        ("median", box.median),
        ("q3", box.q3),
        ("upper fence", box.upper_fence),
        ("mean", box.mean),
    ):
        if value is not None:
            yield StatisticRowFact(name=f"{box.label} {name}", value=str(value))
    yield StatisticRowFact(name=f"{box.label} outliers", value=str(box.outlier_count))


def _row_facts(row: EdaStatisticRow) -> Iterator[StatisticRowFact]:
    """A row's value, p-value and interval, each a value of its own."""
    for name, value in (
        (row.name, row.value),
        (f"{row.name} p-value", row.p_value),
        (f"{row.name} confidence interval", row.confidence_interval),
    ):
        if value is not None:
            yield StatisticRowFact(name=name, value=value)


def statistics_fact(part: EdaStatisticsPart) -> StatisticFact:
    """Each value the part shows, under the name a reference gives it."""
    return StatisticFact(
        id=part.statistic_id,
        kind=part.kind,
        title=part.title,
        rows=[
            *(fact for row in part.rows for fact in _row_facts(row)),
            *(fact for box in part.boxes for fact in _box_rows(box)),
        ],
    )


__all__ = [
    "StatisticFact",
    "StatisticKind",
    "StatisticRowFact",
    "pca_fact",
    "statistic_id",
    "statistic_references",
    "statistic_value",
    "statistics_fact",
]
