"""A source an answer names, by the identifiers a reader opens it with."""

from __future__ import annotations

from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator

type CitationKind = Literal["record", "literature", "web"]


class SourceReference(CamelModel):
    """One source an answer names, by the identifiers a reader opens it with."""

    model_config = ConfigDict(frozen=True)

    kind: CitationKind
    label: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "What the reader sees: the gene id and the site for a record, the "
            "title for a paper or a page."
        ),
    )
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None

    @model_validator(mode="after")
    def _a_source_can_be_opened(self) -> Self:
        if not self.references():
            msg = "a source carries a url, a DOI or a PMID"
            raise ValueError(msg)
        return self

    def references(self) -> list[str]:
        """Every identifier this source is checked by."""
        return [value for value in (self.url, self.doi, self.pmid) if value]


class Citation(SourceReference):
    """One source the check retrieved, and what it settles."""

    why: str = Field(min_length=1, max_length=300)


__all__ = ["Citation", "CitationKind", "SourceReference"]
