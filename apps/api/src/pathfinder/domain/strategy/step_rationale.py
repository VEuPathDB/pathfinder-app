"""Why a step runs what it runs: the search choice FRAME recorded against the
catalog's answer, or the compute an analysis step's document holds."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import ConfigDict, Discriminator, Field, ValidationInfo, field_validator
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding

__all__ = [
    "AnalysisRationale",
    "ComparedSearch",
    "RationaleBasis",
    "SearchRationale",
    "StepRationale",
    "names_the_phrase",
    "said_beside",
]

RationaleBasis = Literal[
    "parameter", "organism", "record_type", "only_match", "nearest"
]

_SHORT: dict[RationaleBasis, str] = {
    "parameter": "sets {term}",
    "organism": "covers {term}",
    "record_type": "returns {term}",
    "only_match": "only search naming {term}",
    "nearest": "nearest to {term}",
}

# A paragraph ends at a blank line, and a top-level list item starts a block of
# its own. An indented line or sub-bullet belongs to the item above it.
_BLOCK_BREAK = re.compile(r"\n\s*\n|\n(?= ?(?:[-*+]|\d+\.)\s)")


class ComparedSearch(CamelModel):
    """A search the catalog answered beside the bound one, as that answer scored it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    display_name: str
    similarity: float | None = None

    def label(self) -> str:
        """The display name, with its score when the answer scored it."""
        if self.similarity is None:
            return self.display_name
        return f"{self.display_name} {self.similarity:.2f}"


class SearchRationale(CamelModel):
    """Why a criterion runs its search, against what the catalog answered.

    The tool writes every field but ``basis``, ``term`` and ``reason`` from the
    catalog read it recorded, so the comparison is what FRAME saw.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    kind: Literal["search"] = "search"
    search_name: str
    basis: RationaleBasis
    # What decides it, as the researcher reads it: a parameter's display name,
    # an organism, a record type, or the phrase no other search names.
    term: str
    reason: str = Field(max_length=160)
    # The bound search's own score in the read, None for a listing.
    similarity: float | None = None
    compared: list[ComparedSearch] = Field(default_factory=list, max_length=3)
    answered: int = 0
    query: str = ""
    tool_call_id: str
    # The urls, DOIs and PMIDs this turn retrieved that FRAME cites for it.
    sources: list[str] = Field(default_factory=list)
    # The label every surface shows, always derived from the basis and the term.
    short: str = Field(default="", validate_default=True)

    @field_validator("short", mode="after")
    @classmethod
    def _labelled(cls, given: str, info: ValidationInfo) -> str:
        if "basis" not in info.data or "term" not in info.data:
            return given
        return _SHORT[info.data["basis"]].format(term=info.data["term"])

    def line(self) -> str:
        """The reason, and the searches it was chosen over."""
        if not self.compared:
            return self.reason
        over = ", ".join(search.label() for search in self.compared)
        return f"{self.reason} (over {over})"


class AnalysisRationale(CamelModel):
    """Why an analysis step selects its genes: the compute its document holds."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    kind: Literal["analysis"] = "analysis"
    dataset_id: str
    method: str | None = None
    # The method, else the first subset filter.
    term: str
    reason: str
    # The label every surface shows, always derived from the method.
    short: str = Field(default="", validate_default=True)

    @classmethod
    def of(cls, binding: AnalysisBinding) -> AnalysisRationale:
        term = binding.method or next(iter(binding.subset), binding.dataset_id)
        return cls(
            dataset_id=binding.dataset_id,
            method=binding.method,
            term=term,
            reason=binding.words,
        )

    @field_validator("short", mode="after")
    @classmethod
    def _labelled(cls, _given: str, info: ValidationInfo) -> str:
        method = info.data.get("method")
        return "analysis subset" if method is None else f"computed by {method}"

    def line(self) -> str:
        return self.reason


StepRationale = Annotated[SearchRationale | AnalysisRationale, Discriminator("kind")]


def names_the_phrase(prose: str, phrase: str) -> bool:
    """Whether the prose holds the phrase whole, in any case."""
    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, prose, flags=re.IGNORECASE) is not None


def said_beside(prose: str, name: str, term: str) -> bool:
    """Whether one paragraph or one list item names both the search and the term."""
    return any(
        names_the_phrase(block, name) and names_the_phrase(block, term)
        for block in _BLOCK_BREAK.split(prose)
    )
