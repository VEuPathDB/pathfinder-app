"""The disputed findings a reply names once it reads a fact that lists them."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from pathfinder.domain.reference_grammar import A_REFERENCE, reference_kind
from pathfinder.domain.statistic_facts import StatisticFact

DISPUTED = "disputed"


@dataclass(frozen=True)
class UnnamedDispute:
    token: str
    reference: str


def _place(name: str) -> str | None:
    head, _, rest = name.partition(".")
    place = rest.partition(".")[0]
    return place if head == DISPUTED and place.isdigit() else None


def unnamed_disputes(
    prose: str, statistics: Sequence[StatisticFact]
) -> Iterator[UnnamedDispute]:
    bodies = [
        match.group("body") or ""
        for match in A_REFERENCE.finditer(prose)
        if reference_kind(match) in {"stat", "cite"}
    ]
    for fact in statistics:
        prefix = f"{fact.id}."
        read = [body.removeprefix(prefix) for body in bodies if body.startswith(prefix)]
        if not read:
            continue
        named = {_place(body) for body in read}
        for place in dict.fromkeys(_place(row.name) for row in fact.rows):
            if place is not None and place not in named:
                yield UnnamedDispute(
                    token=f"[stat:{fact.id}.{DISPUTED}.{place}.id]",
                    reference=f"[cite:{fact.id}.{DISPUTED}.{place}.disagreementText]",
                )


__all__ = ["DISPUTED", "UnnamedDispute", "unnamed_disputes"]
