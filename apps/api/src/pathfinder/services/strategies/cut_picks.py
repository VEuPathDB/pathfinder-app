"""A multi-pick taken from a vocabulary read: a list cut from more entries, or
a lookup, and the picked entries whose label holds no word of the looked-up
concept."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import VocabLookup

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
)

_WORD = re.compile(r"[^\W_]+")


def _words(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(text.casefold()))


class OptionsRead(BaseModel):
    """One parameter read a pick can come from. ``total`` is the count the
    shown list was cut from, None when the list travelled whole."""

    model_config = ConfigDict(frozen=True)

    param: str
    shown: frozenset[str]
    total: int | None = None
    lookup: VocabLookup | None = None

    def reading(self) -> str:
        """The terms the read matched, quoted; empty for a read with no query."""
        return (
            ", ".join(f"'{term}'" for term in self.lookup.terms) if self.lookup else ""
        )

    def _is_cut(self, picks: Sequence[str]) -> bool:
        return (
            self.total is not None
            and self.total > len(self.shown)
            and set(picks) <= self.shown
        )

    def taken(self, picks: Sequence[str]) -> Measurement | None:
        """How many entries of the read the pick took, and of how many. A read
        that lists no entry, as a tree read lists none, counts no pick."""
        if not self.shown:
            return None
        if self._is_cut(picks):
            return Measurement(
                kind="picked_from_a_cut_list",
                param=self.param,
                count=len(picks),
                unchosen_count=(self.total or 0) - len(picks),
                reading=self.reading(),
            )
        if self.lookup is None or self.total is not None:
            return None
        matched = len(self.shown & set(picks))
        return Measurement(
            kind="picked_from_a_lookup",
            param=self.param,
            count=matched,
            unchosen_count=len(self.shown) - matched,
            reading=self.reading(),
        )

    def label_gaps(self, labels: Sequence[str]) -> list[Measurement]:
        """Each label that holds no word of any term the lookup read."""
        if self.lookup is None:
            return []
        concept = frozenset().union(*(_words(t) for t in self.lookup.terms))
        return [
            Measurement(
                kind="label_without_the_concept",
                param=self.param,
                label=label,
                reading=self.reading(),
            )
            for label in labels
            if not _words(label) & concept
        ]


def read_picks(criterion: Criterion, reads: Sequence[OptionsRead]) -> list[Measurement]:
    """For each read of a parameter the criterion picks on: how many of the
    entries the read showed the pick took, and each picked label that holds no
    word of the looked-up concept. A pick with no label is not judged."""
    measured: list[Measurement] = []
    for read in reads:
        match criterion.resolved_params.get(read.param):
            case BoundValue(value=MultiPickValue(values=picks)):
                labels = [
                    m.label
                    for m in criterion.measurements
                    if m.kind == "vocabulary_label"
                    and m.param == read.param
                    and m.reading in picks
                ]
                taken = read.taken(picks)
                measured.extend([*([taken] if taken else []), *read.label_gaps(labels)])
            case _:
                pass
    return measured
