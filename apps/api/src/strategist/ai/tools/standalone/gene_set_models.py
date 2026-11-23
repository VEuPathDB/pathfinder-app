"""Gene set response models."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
)
from veupathdb.domain.parameters import ParamValue

from strategist.services.gene_sets.types import GeneSetSource, OutOfDate

_A_LIST_AND_A_STEP = (
    "A pasted list of gene ids carries no strategy step. Leave step_id out to save "
    "these ids as a list, or leave gene_ids out to save the genes of that step."
)


class _NamedStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str | None = None


def _held_by_no_step(gene_ids: list[str], info: ValidationInfo) -> list[str]:
    if _NamedStep.model_validate(info.data).step_id is not None:
        raise ValueError(_A_LIST_AND_A_STEP)
    return gene_ids


GeneSetName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PastedGeneIds = Annotated[
    list[str], Field(min_length=1), AfterValidator(_held_by_no_step)
]


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


LISTING_PAGE = 25


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
    saved_here: bool = False
    saved_on: str = ""
    """The site the set was saved on."""
    genes_on_this_site: int = 0
    record_noun: str = "gene"
    out_of_date: OutOfDate | None = None


class UploadedGeneList(CamelModel):
    name: str
    value: str
    search_name: str
    parameter: str


class GeneSetListResponse(CamelModel):
    gene_sets: list[GeneSetListItem] = Field(default_factory=list)
    total_sets: int = 0
    uploaded_lists: list[UploadedGeneList] = Field(default_factory=list)
    total_uploaded_lists: int = 0
    uploads_unread: bool = False
    next_offset: int | None = None
