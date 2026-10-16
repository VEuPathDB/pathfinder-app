"""The records a turn read or listed, as its facts part shows them."""

from __future__ import annotations

from collections.abc import Callable

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.evidence import GeneFit
from pathfinder.domain.record_page import ListedRecord


class OrthologFact(CamelModel):
    model_config = ConfigDict(frozen=True)

    gene_id: str
    organism: str = ""


class SourceFact(CamelModel):
    """A record or a reference a read returned, the step whose listing gave the
    record, and the check's judgement of the record against the request.

    ``values`` are the record's other words, its gene name and its chromosome;
    ``orthologs`` are its orthologs in the one organism the read asked for.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    record_id: str = ""
    product: str = ""
    organism: str = ""
    values: list[str] = Field(default_factory=list)
    orthologs: list[OrthologFact] = Field(default_factory=list)
    step_id: str = ""
    step_name: str = ""
    fit: GeneFit | None = None
    why: str = ""

    def _words(self) -> list[str]:
        paired = [t for o in self.orthologs for t in (o.gene_id, o.organism)]
        return [t for t in (self.product, self.organism, *self.values, *paired) if t]

    def _fit(self) -> str:
        return "" if self.fit is None else f" (the check judged its fit {self.fit})"

    def described(self) -> str:
        """The record's id and words, its fit, and its link."""
        named = ", ".join(t for t in (self.record_id, *self._words()) if t)
        return f"{named}{self._fit()}: {self.url}" if named else self.url

    def where(self) -> str:
        return f"Read from {self.step_name}" if self.step_name else "Read"

    def line(self) -> str:
        return f"{self.where()}: {self.described()}"

    def redacted(self, redact: Callable[[str], str]) -> SourceFact:
        return self.model_copy(
            update={
                "url": redact(self.url),
                "product": redact(self.product),
                "organism": redact(self.organism),
                "values": [redact(value) for value in self.values],
                "orthologs": [
                    o.model_copy(update={"organism": redact(o.organism)})
                    for o in self.orthologs
                ],
                "step_name": redact(self.step_name),
                "why": redact(self.why),
            }
        )


class ListedFact(CamelModel):
    """The ids a listing or a sample of one step returned, under that step."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    step_name: str = ""
    records: list[ListedRecord] = Field(default_factory=list)

    def line(self) -> str:
        ids = ", ".join(r.record_id for r in self.records)
        return f"Listed from {self.step_name}: {ids}"

    def redacted(self, redact: Callable[[str], str]) -> ListedFact:
        return self.model_copy(update={"step_name": redact(self.step_name)})
