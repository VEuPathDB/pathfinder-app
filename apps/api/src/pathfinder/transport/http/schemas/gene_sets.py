"""HTTP request/response schemas for gene sets."""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.parameters.values import ParamValue
from veupathdb_mcp.wdk import SetOperation
from veupathdb_mcp.wdk.enrichment import EnrichmentAnalysisType, EnrichmentResult

from pathfinder.services.gene_sets.types import GeneSetSource
from pathfinder.transport.http.schemas.site_id import SiteId


class CreateGeneSetRequest(CamelModel):
    """Request to create a gene set from IDs, a strategy, or an upload."""

    name: str = Field(min_length=1, max_length=200)
    site_id: SiteId
    gene_ids: list[str]
    source: GeneSetSource = "paste"
    wdk_strategy_id: int | None = Field(None)
    wdk_step_id: int | None = Field(None)
    search_name: str | None = Field(None, max_length=255)
    record_type: str | None = Field(None, max_length=100)
    parameters: dict[str, ParamValue] | None = None


class GeneSetResponse(CamelModel):
    """A gene set, as returned to the client."""

    id: str
    name: str
    site_id: str
    gene_ids: list[str]
    source: GeneSetSource
    gene_count: int
    wdk_strategy_id: int | None = Field(None)
    wdk_step_id: int | None = Field(None)
    search_name: str | None = Field(None)
    record_type: str | None = Field(None)
    parameters: dict[str, ParamValue] | None = None
    parent_set_ids: list[str] = Field(default_factory=list)
    operation: SetOperation | None = None
    created_at: str
    step_count: int = Field(1)
    enrichment_results: list[EnrichmentResult] = Field(default_factory=list)
    """Enrichment results already computed for this set."""
    vdi_id: str | None = None
    """The VEuPathDB user dataset this set was published to, when it was."""


# A model's docstring is published as its schema description, so these two
# stay undocumented until the described text is part of the contract.
class GeneSetImportRequest(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    site_id: SiteId
    raw_text: str


class GeneSetExportResponse(CamelModel):
    export_id: str
    filename: str
    content_type: str
    url: str


class SetOperationRequest(CamelModel):
    """Request to combine two gene sets with a set operation."""

    set_a_id: str
    set_b_id: str
    operation: SetOperation
    name: str = Field(min_length=1, max_length=200)


class GeneSetEnrichRequest(CamelModel):
    """Request to run enrichment on a gene set."""

    enrichment_types: list[EnrichmentAnalysisType]


class EnsembleScoringRequest(CamelModel):
    """Request to compute ensemble frequency scores across gene sets."""

    gene_set_ids: list[str] = Field(min_length=2)
    positive_controls: list[str] | None = Field(None)


class ReverseSearchRequest(CamelModel):
    """Request to rank a user's gene sets by recall of the given genes."""

    positive_gene_ids: list[str] = Field(min_length=1)
    negative_gene_ids: list[str] | None = Field(None)
    site_id: SiteId


class ReverseSearchResultItem(CamelModel):
    """One ranked gene set in a reverse-search result."""

    gene_set_id: str
    name: str
    search_name: str | None = Field(None)
    recall: float
    precision: float
    f1: float
    estimated_size: int
    overlap_count: int


class GeneConfidenceRequest(CamelModel):
    """Request to compute per-gene confidence scores from classification data."""

    tp_ids: list[str]
    fp_ids: list[str]
    fn_ids: list[str]
    tn_ids: list[str]
    ensemble_scores: dict[str, float] | None = Field(None)
    enrichment_gene_counts: dict[str, int] | None = Field(None)
    max_enrichment_terms: int = Field(1, ge=1)


class GeneConfidenceScoreResponse(CamelModel):
    """One gene confidence score."""

    gene_id: str
    composite_score: float
    classification_score: float
    ensemble_score: float
    enrichment_score: float
