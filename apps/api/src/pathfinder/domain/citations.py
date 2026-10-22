"""A source an answer names, by the identifiers a reader opens it with."""

from __future__ import annotations

from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.clipped import text_clipped_to

type CitationKind = Literal["record", "literature", "web"]


class SourceReference(CamelModel):
    """One source an answer names, by the identifiers a reader opens it with."""

    model_config = ConfigDict(frozen=True)

    kind: CitationKind
    label: Annotated[str, text_clipped_to(200)] = Field(
        min_length=1,
        description=(
            "What the reader sees: the gene id and the site for a record, the "
            "title for a paper or a page."
        ),
    )
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None

    def references(self) -> list[str]:
        """Every identifier this source is checked by."""
        return [value for value in (self.url, self.doi, self.pmid) if value]


class Citation(SourceReference):
    """One source the check retrieved, and what it settles."""

    why: Annotated[str, text_clipped_to(300)] = Field(min_length=1)


__all__ = ["Citation", "CitationKind", "SourceReference"]
