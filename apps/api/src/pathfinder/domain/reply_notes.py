"""The numbered notes a reply's ``cite`` references render as, below the reply."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pathfinder.domain.reference_grammar import A_REFERENCE, reference_kind
from pathfinder.domain.statistic_facts import (
    StatisticFact,
    StatisticRowFact,
    statistic_row,
)

type KindMismatch = Literal["sentence_in_place", "cited_number"]


@dataclass(frozen=True)
class MisusedReference:
    kind: KindMismatch
    token: str
    reference: str


def misused_references(
    prose: str, statistics: Sequence[StatisticFact]
) -> Iterator[MisusedReference]:
    for match in A_REFERENCE.finditer(prose):
        body = match.group("body") or ""
        row = statistic_row(statistics, body)
        if row is None:
            continue
        match reference_kind(match), row.form:
            case "stat", "sentence":
                yield MisusedReference(
                    "sentence_in_place", match.group(), f"[cite:{body}]"
                )
            case "cite", "number":
                yield MisusedReference("cited_number", match.group(), f"[stat:{body}]")
            case _:
                continue


@dataclass
class ReplyNotes:
    statistics: Sequence[StatisticFact]
    label: str = ""
    numbered: dict[str, tuple[int, StatisticRowFact]] = field(default_factory=dict)

    def marker(self, body: str) -> str | None:
        row = statistic_row(self.statistics, body)
        if row is None:
            return None
        number, _ = self.numbered.setdefault(body, (len(self.numbered) + 1, row))
        return f"[^{self.label}{number}]"

    def block(self) -> str:
        if not self.numbered:
            return ""
        notes = "\n".join(
            f"[^{self.label}{n}]: {row.note()}" for n, row in self.numbered.values()
        )
        return f"\n\n{notes}"


__all__ = ["KindMismatch", "MisusedReference", "ReplyNotes", "misused_references"]
