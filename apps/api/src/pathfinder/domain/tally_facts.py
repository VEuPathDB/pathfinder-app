"""The counts a column tally of a turn returned, which a reply's ``tally``
references render."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.count_words import counted
from pathfinder.domain.reference_grammar import (
    A_REFERENCE,
    TALLY_VALUES,
    reference_kind,
)

type TallyFilter = tuple[str, tuple[str, ...]]

VALUE_NOUN = "value"


def tally_id(
    site_id: str, search_name: str, column: str, only: TallyFilter | None
) -> str:
    """The id of one tally of a search's column, the same on every read."""
    key = json.dumps(
        [site_id, search_name, column, None if only is None else [only[0], *only[1]]]
    )
    return f"tally_{hashlib.sha256(key.encode()).hexdigest()[:8]}"


class TallyRowFact(CamelModel):
    model_config = ConfigDict(frozen=True)

    value: str
    count: int
    label: str = ""


class TallyFact(CamelModel):
    """One column of one search, counted by each of its values."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    record_noun: str
    total: int
    distinct: int
    rows: list[TallyRowFact] = Field(default_factory=list)
    wdk_step_id: int | None = None

    def counts_another_step(self, result_step_id: int | None) -> bool:
        return (
            self.wdk_step_id is not None
            and result_step_id is not None
            and self.wdk_step_id != result_step_id
        )

    def heading(self, result_step_id: int | None) -> str:
        if not self.counts_another_step(result_step_id):
            return self.title
        return (
            f"{self.title}, counted on step {self.wdk_step_id}, not on the result "
            f"step {result_step_id}"
        )

    def count(self, value: str) -> int | None:
        """The records that hold the value, or the total for no value."""
        if value == "":
            return self.total
        return next((row.count for row in self.rows if row.value == value), None)

    def lines(self, result_step_id: int | None = None) -> list[str]:
        return [
            self.heading(result_step_id),
            f"[tally:{self.id}] = {counted(self.total, self.record_noun)}",
            f"[tally:{self.id}{TALLY_VALUES}] = {self.distinct:,}",
            *(f"[tally:{self.id}.{row.value}] = {row.count}" for row in self.rows),
        ]

    def redacted(self, redact: Callable[[str], str]) -> TallyFact:
        return self.model_copy(update={"title": redact(self.title)})


def tally_count(tallies: Sequence[TallyFact], body: str) -> str | None:
    """The count a ``tally`` reference names as ``<id>`` or ``<id>.<value>``,
    in the tally's noun, or the number of values ``<id>:values`` names."""
    by_id = {t.id: t for t in tallies}
    if body.endswith(TALLY_VALUES) and body.removesuffix(TALLY_VALUES) in by_id:
        return f"{by_id[body.removesuffix(TALLY_VALUES)].distinct:,}"
    held_id, _, value = body.partition(".")
    tally = by_id.get(held_id)
    if tally is None:
        return None
    count = tally.count(value)
    return None if count is None else counted(count, tally.record_noun)


def tally_references(tallies: Sequence[TallyFact], number: str) -> Iterator[str]:
    """Each ``tally`` reference whose count is the number."""
    for tally in tallies:
        if str(tally.total) == number:
            yield f"[tally:{tally.id}]"
        if str(tally.distinct) == number:
            yield f"[tally:{tally.id}{TALLY_VALUES}]"
        for row in tally.rows:
            if str(row.count) == number:
                yield f"[tally:{tally.id}.{row.value}]"


def _tally_id(match: re.Match[str]) -> str:
    body = match.group("body") or ""
    return body.removesuffix(TALLY_VALUES).partition(".")[0]


def tallies_of_another_step(
    prose: str, tallies: Sequence[TallyFact], result_step_id: int | None
) -> list[str]:
    if result_step_id is not None and any(
        t.wdk_step_id == result_step_id for t in tallies
    ):
        return []
    elsewhere = {t.id for t in tallies if t.counts_another_step(result_step_id)}
    return [
        match.group()
        for match in A_REFERENCE.finditer(prose)
        if reference_kind(match) == "tally" and _tally_id(match) in elsewhere
    ]
