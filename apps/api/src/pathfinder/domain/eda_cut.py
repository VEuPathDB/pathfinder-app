from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.question_options import (
    PickClass,
    PickTail,
    TailRule,
    TypedOption,
    option_id,
)
from pathfinder.domain.strategy.questions import OpenQuestion

_OPTIONS_LIMIT = 8

TAIL_RULES = (
    TailRule(end="low", percent=5),
    TailRule(end="low", percent=10),
    TailRule(end="high", percent=5),
    TailRule(end="high", percent=10),
)


class NumericBin(CamelModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    bin_start: float
    bin_end: float
    value: int


class TailEdge(CamelModel):
    model_config = ConfigDict(frozen=True)

    rule: TailRule
    bound: float
    count: int
    total: int

    @property
    def side(self) -> Literal["at most", "at least"]:
        return "at most" if self.rule.end == "low" else "at least"

    @property
    def wire_end(self) -> Literal["max", "min"]:
        return "max" if self.rule.end == "low" else "min"

    def binds(self, at_least: float | None, at_most: float | None) -> bool:
        if self.rule.end == "low":
            return at_least is None and at_most == self.bound
        return at_most is None and at_least == self.bound

    def cut(self, noun: str) -> str:
        return f"{self.side} {self.bound:g} ({self.count} {noun})"

    def label(self, name: str, noun: str) -> str:
        word = "Lowest" if self.rule.end == "low" else "Highest"
        share = 100 * self.count / self.total
        return f"{word} {share:.1f}% of {name}: {self.cut(noun)}"


class ClassCount(CamelModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str
    variable_id: str
    variable_name: str
    value: str
    count: int

    def label(self, noun: str) -> str:
        return f"{self.variable_name}: {self.value} ({self.count} {noun})"


def _at_shown_precision(edge: float) -> float:
    return float(f"{edge:g}")


def tail_edge(bins: Sequence[NumericBin], rule: TailRule) -> TailEdge | None:
    total = sum(b.value for b in bins)
    ordered = sorted(bins, key=lambda b: b.bin_start, reverse=rule.end == "high")
    held = 0
    for each in ordered:
        held += each.value
        if 100 * held >= rule.percent * total > 0:
            if held == total:
                return None
            edge = each.bin_end if rule.end == "low" else each.bin_start
            return TailEdge(
                rule=rule, bound=_at_shown_precision(edge), count=held, total=total
            )
    return None


def tail_edges(bins: Sequence[NumericBin]) -> list[TailEdge]:
    edges: list[TailEdge] = []
    for rule in TAIL_RULES:
        edge = tail_edge(bins, rule)
        if edge is not None and all(
            (e.rule.end, e.bound) != (rule.end, edge.bound) for e in edges
        ):
            edges.append(edge)
    return edges


def _option(label: str, binding: PickTail | PickClass) -> TypedOption:
    return TypedOption(id=option_id(label), label=label, binding=binding)


def cut_question(
    name: str,
    noun: str,
    tails: Sequence[TailEdge],
    classes: Sequence[ClassCount],
) -> OpenQuestion:
    options = [
        *(_option(e.label(name, noun), PickTail(rule=e.rule)) for e in tails),
        *(
            _option(
                c.label(noun),
                PickClass(
                    entity_id=c.entity_id, variable_id=c.variable_id, value=c.value
                ),
            )
            for c in classes
        ),
    ]
    return OpenQuestion(
        question=f"Which cut of {name} selects the {noun} you mean?",
        options=options[:_OPTIONS_LIMIT],
    )
