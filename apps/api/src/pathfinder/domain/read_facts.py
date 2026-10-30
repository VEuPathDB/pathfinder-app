from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.written_links import written_links

_SHOWN_DEPTH = 2
_SHOWN_ROWS = 40
_A_CAPITAL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_A_MARK = re.compile(r"([\[\]()!<>`*])")


def _escaped(text: str) -> str:
    return _A_MARK.sub(r"\\\1", text)


class ReadRow(CamelModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class ReadFact(CamelModel):
    model_config = ConfigDict(frozen=True)

    title: str
    rows: list[ReadRow] = Field(default_factory=list)

    def lines(self) -> list[str]:
        return [self.title, *(f"{row.label}: {row.value}" for row in self.rows)]

    def markdown(self) -> str:
        rows = (f"- {_escaped(row.label)}: {_escaped(row.value)}" for row in self.rows)
        return "\n".join([f"**{_escaped(self.title)}**", *rows])

    def redacted(self, redact: Callable[[str], str]) -> ReadFact:
        return self.model_copy(update={"title": redact(self.title)})


def _named(row: StatisticRowFact) -> list[str]:
    return [part for part in row.name.split(".") if not part.isdigit()]


def _label(named: Sequence[str]) -> str:
    kept = [p for i, p in enumerate(named) if i == 0 or p != named[i - 1]]
    return " ".join(_A_CAPITAL.sub(" ", part).lower() for part in kept[-2:])


def _shown(row: StatisticRowFact) -> bool:
    return len(_named(row)) <= _SHOWN_DEPTH and not written_links(row.value)


def read_fact(fact: StatisticFact) -> ReadFact:
    rows = [
        ReadRow(label=_label(_named(row)), value=row.value)
        for row in fact.rows
        if _shown(row)
    ]
    return ReadFact(title=fact.title, rows=rows[:_SHOWN_ROWS])


__all__ = ["ReadFact", "ReadRow", "read_fact"]
