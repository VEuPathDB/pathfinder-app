from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import VocabLookup, VocabOption, name_past_accession


class LookupRecord(BaseModel):
    """The entries the lookups of one parameter matched this pass, each with the
    query term that matched it first."""

    model_config = ConfigDict(frozen=True)

    matched: dict[str, str] = Field(default_factory=dict)
    same_named: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    def merged(
        self, lookup: VocabLookup, options: Sequence[VocabOption]
    ) -> LookupRecord:
        found = {value: m.term for m in lookup.matches for value in m.values}
        named = {o.value: name_past_accession(o) for o in options}
        groups = {named[g[0]]: tuple(g) for g in lookup.same_named}
        return LookupRecord(
            matched={**found, **self.matched}, same_named={**groups, **self.same_named}
        )

    def matched_by(self, term: str) -> list[str]:
        return [value for value, first in self.matched.items() if first == term]
