"""The numbered notes a reply's word references render as where they close a clause."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from pathfinder.domain.reference_grammar import A_REFERENCE
from pathfinder.domain.statistic_facts import (
    StatisticFact,
    StatisticRowFact,
    statistic_row,
)

_A_MARKER_GAP = re.compile(r"(?<=[\w*)\]])[ \t]+(?=\[\^\d+\])")


def closes_clause(prose: str, end: int) -> bool:
    index = end
    while index < len(prose):
        if prose[index] in " \t":
            index += 1
            continue
        reference = A_REFERENCE.match(prose, index)
        if reference is None:
            return not prose[index].isalnum()
        index = reference.end()
    return True


@dataclass
class ReplyNotes:
    statistics: Sequence[StatisticFact]
    numbered: dict[str, tuple[int, StatisticRowFact]] = field(default_factory=dict)

    def marker(self, match: re.Match[str]) -> str | None:
        body = match.group("body") or ""
        row = statistic_row(self.statistics, body)
        if row is None or row.form != "word" or match.group("noun"):
            return None
        if not closes_clause(match.string, match.end()):
            return None
        number, _ = self.numbered.setdefault(body, (len(self.numbered) + 1, row))
        return f"[^{number}]"

    def appended(self, text: str) -> str:
        if not self.numbered:
            return text
        notes = "\n".join(f"[^{n}]: {row.note()}" for n, row in self.numbered.values())
        return f"{_A_MARKER_GAP.sub('', text)}\n\n{notes}"


__all__ = ["ReplyNotes", "closes_clause"]
