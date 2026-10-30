"""The counts a column tally of a turn returned."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.count_words import counted
from pathfinder.domain.tally_paths import TallyPath

type TallyFilter = tuple[str, tuple[str, ...]]


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
    path: TallyPath | None = None

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

    def lines(self, result_step_id: int | None = None) -> list[str]:
        return [
            self.heading(result_step_id),
            f"In all: {counted(self.total, self.record_noun)}",
            f"Values: {self.distinct:,}",
            *(f"{row.value}: {row.count:,}" for row in self.rows),
        ]

    def redacted(self, redact: Callable[[str], str]) -> TallyFact:
        return self.model_copy(update={"title": redact(self.title)})
