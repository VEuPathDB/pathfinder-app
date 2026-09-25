"""Why a step runs what it runs: the search choice FRAME recorded against the
catalog's answer, or the compute an analysis step's document holds."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import computed
from pydantic import ConfigDict, Discriminator, Field, ValidationInfo, field_validator
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding

__all__ = [
    "MAX_REASON_CHARS",
    "AnalysisRationale",
    "ChosenRationale",
    "ComparedSearch",
    "ControlsInforms",
    "ControlsRationale",
    "ControlsSource",
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


# A reason is one line a reply can repeat beside the step.
MAX_REASON_CHARS = 160


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
    reason: str = Field(max_length=MAX_REASON_CHARS)
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

    def texts(self) -> list[str]:
        """Every text a model or a researcher wrote into this reason."""
        return [self.reason, self.term, self.query, *self.sources]

    def redacted(self, redact: Callable[[str], str]) -> SearchRationale:
        """This reason with every written text redacted, the label derived again."""
        return SearchRationale.model_validate(
            self.model_dump(by_alias=True)
            | {
                "reason": redact(self.reason),
                "term": redact(self.term),
                "query": redact(self.query),
                "sources": [redact(s) for s in self.sources],
            }
        )


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

    def texts(self) -> list[str]:
        """Every text a model or a researcher wrote into this reason."""
        return [self.reason, self.term]


# Where a separation run found the candidate a criterion runs.
ControlsSource = Literal["thread", "literature", "enrichment", "annotation", "catalog"]
# Which control set the criterion's search returns more of than chance, if either.
ControlsInforms = Literal["recovering", "excluding", "neither"]


class ControlsRationale(CamelModel):
    """Why a criterion runs its search: the controls it separated, as WDK counted them.

    Every count is the criterion's own measured step, never a model's estimate.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    kind: Literal["controls"] = "controls"
    task_id: str
    search_name: str
    source: ControlsSource
    basis: str
    # The reference of a literature candidate, kept when a read of the turn returned it.
    sources: list[str] = Field(default_factory=list)
    informs: ControlsInforms
    recovered: int = Field(ge=0)
    positives: int = Field(ge=0)
    admitted: int = Field(ge=0)
    negatives: int = Field(ge=0)
    result_size: int = Field(ge=0)

    @computed
    def term(self) -> str:
        """The count that decides the choice."""
        if self.informs == "excluding":
            return f"{self.admitted} of {self.negatives} negatives"
        return f"{self.recovered} of {self.positives} positives"

    @computed
    def short(self) -> str:
        """The label every surface shows."""
        return (
            f"recovers {self.recovered} of {self.positives} positives, "
            f"admits {self.admitted} of {self.negatives} negatives"
        )

    def line(self) -> str:
        """The counts, the result size and what the candidate was drawn from."""
        return (
            f"chosen by the controls: {self.short}, {self.result_size:,} genes "
            f"({self.basis})"
        )

    def texts(self) -> list[str]:
        """Every text a model or a researcher wrote into this reason."""
        return [self.basis, *self.sources]

    def redacted(self, redact: Callable[[str], str]) -> ControlsRationale:
        """This reason with every written text redacted. The counts stay."""
        return self.model_copy(
            update={
                "basis": redact(self.basis),
                "sources": [redact(s) for s in self.sources],
            }
        )


# Why a criterion runs its search: the binding pass's choice, or the controls'.
ChosenRationale = Annotated[SearchRationale | ControlsRationale, Discriminator("kind")]

StepRationale = Annotated[
    SearchRationale | AnalysisRationale | ControlsRationale, Discriminator("kind")
]


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
