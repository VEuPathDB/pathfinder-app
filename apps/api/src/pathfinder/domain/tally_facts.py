"""The counts a column tally of a turn returned, which a reply's ``tally``
references render."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.count_words import counted

type TallyFilter = tuple[str, tuple[str, ...]]

VALUE_NOUN = "value"
_VALUES = ":values"


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


class TallyFact(CamelModel):
    """One column of one search, counted by each of its values."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    record_noun: str
    total: int
    distinct: int
    rows: list[TallyRowFact] = Field(default_factory=list)

    def count(self, value: str) -> int | None:
        """The records that hold the value, or the total for no value."""
        if value == "":
            return self.total
        return next((row.count for row in self.rows if row.value == value), None)

    def lines(self) -> list[str]:
        return [
            self.title,
            f"[tally:{self.id}] = {counted(self.total, self.record_noun)}",
            f"[tally:{self.id}{_VALUES}] = {counted(self.distinct, VALUE_NOUN)}",
            *(f"[tally:{self.id}.{row.value}] = {row.count}" for row in self.rows),
        ]

    def redacted(self, redact: Callable[[str], str]) -> TallyFact:
        return self.model_copy(update={"title": redact(self.title)})


def tally_count(tallies: Sequence[TallyFact], body: str) -> str | None:
    """The count a ``tally`` reference names as ``<id>`` or ``<id>.<value>``,
    in the tally's noun, or the values ``<id>:values`` names."""
    by_id = {t.id: t for t in tallies}
    if body.endswith(_VALUES) and body.removesuffix(_VALUES) in by_id:
        return counted(by_id[body.removesuffix(_VALUES)].distinct, VALUE_NOUN)
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
            yield f"[tally:{tally.id}{_VALUES}]"
        for row in tally.rows:
            if str(row.count) == number:
                yield f"[tally:{tally.id}.{row.value}]"
