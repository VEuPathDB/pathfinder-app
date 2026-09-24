"""Gene set response models."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import ParamValue

from pathfinder.services.gene_sets.types import GeneSetSource


class WdkProvenance(BaseModel):
    """What a saved gene set records about the strategy step behind it.

    It is read from the conversation's strategy, so a set with no WDK step id
    was pasted rather than taken from a step.
    """

    model_config = ConfigDict(frozen=True)

    search_name: str | None = None
    parameters: dict[str, ParamValue] | None = None
    wdk_strategy_id: int | None = None
    wdk_step_id: int | None = None

    @property
    def source(self) -> GeneSetSource:
        """Where the set's genes came from, as the gene-set store records it."""
        return "strategy" if self.wdk_step_id is not None else "paste"


class GeneSetCreatedSummary(CamelModel):
    """Summary of a created gene set."""

    id: str
    name: str
    gene_count: int
    source: GeneSetSource
    site_id: str


class GeneSetCreatedResponse(CamelModel):
    """Response after creating a gene set."""

    gene_set_created: GeneSetCreatedSummary
    message: str


class GeneSetListItem(CamelModel):
    """Summary of a gene set in a list."""

    id: str
    name: str
    gene_count: int
    source: GeneSetSource
    search_name: str | None = None
    has_wdk_step: bool = False


class GeneSetListResponse(CamelModel):
    """Response listing gene sets."""

    gene_sets: list[GeneSetListItem] = Field(default_factory=list)
    total_sets: int = 0
