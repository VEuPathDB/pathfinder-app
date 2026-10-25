"""The certainty a reply gives one gene: its own finding's, never a group's."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from pathfinder.domain.reference_grammar import A_REFERENCE, reference_kind
from pathfinder.domain.reference_placement import clause_texts
from pathfinder.domain.statistic_facts import StatisticFact

CERTAINTY = "certainty"
_GENES = "genes"


@dataclass(frozen=True)
class GroupCertainty:
    token: str
    reference: str


def _scope(name: str) -> str | None:
    if name == CERTAINTY:
        return ""
    head, dot, last = name.rpartition(".")
    return f"{head}{dot}" if last == CERTAINTY and dot else None


def _genes_under(fact: StatisticFact, scope: str, *, direct: bool) -> set[str]:
    def holds(name: str) -> bool:
        rest = name.removeprefix(scope)
        if direct:
            return rest.startswith(f"{_GENES}.")
        return f".{_GENES}." in f".{rest}"

    return {
        row.value for row in fact.rows if row.name.startswith(scope) and holds(row.name)
    }


def _own(statistics: Sequence[StatisticFact], gene: str) -> list[str]:
    return [
        f"{fact.id}.{row.name}"
        for fact in statistics
        for row in fact.rows
        if (scope := _scope(row.name)) is not None
        and gene in _genes_under(fact, scope, direct=True)
    ]


def _grouped(statistics: Sequence[StatisticFact], body: str) -> bool:
    for fact in statistics:
        name = body.removeprefix(f"{fact.id}.")
        scope = None if name == body else _scope(name)
        if scope is not None and fact.value(name) is not None:
            return len(_genes_under(fact, scope, direct=False)) > 1
    return False


def _records(text: str) -> list[str]:
    found = (m for m in A_REFERENCE.finditer(text) if reference_kind(m) == "record")
    return list(dict.fromkeys(m.group("body") or "" for m in found))


def _cited(text: str) -> Iterator[re.Match[str]]:
    for match in A_REFERENCE.finditer(text):
        if reference_kind(match) in {"stat", "cite"}:
            yield match


def group_certainties(
    prose: str, statistics: Sequence[StatisticFact]
) -> Iterator[GroupCertainty]:
    replied = _records(prose)
    for clause in clause_texts(prose):
        genes = _records(clause) or replied
        if len(genes) != 1:
            continue
        own = _own(statistics, genes[0])
        for match in _cited(clause):
            body = match.group("body") or ""
            if own and body not in own and _grouped(statistics, body):
                yield GroupCertainty(token=match.group(), reference=f"[stat:{own[0]}]")


__all__ = ["GroupCertainty", "group_certainties"]
