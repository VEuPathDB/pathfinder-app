"""Workbench and gene set response models."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, Field
from veupathdb.domain.parameters.values import ParamValue
from veupathdb_mcp.wdk.enrichment.types import EnrichmentResult

from pathfinder.services.experiment.types.core import ExperimentStatus
from pathfinder.services.experiment.types.experiment import ExperimentConfig
from pathfinder.services.experiment.types.metrics import (
    CrossValidationResult,
    ExperimentMetrics,
    GeneInfo,
)
from pathfinder.services.gene_sets.types import GeneSetSource


class WdkSourceSpec(BaseModel):
    """WDK provenance info for a gene set."""

    search_name: str | None = None
    parameters: dict[str, ParamValue] | None = None
    wdk_strategy_id: int | None = None
    wdk_step_id: int | None = None


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


class WorkbenchError(CamelModel):
    """Error response from workbench read tools."""

    error: str


class ClassificationCounts(CamelModel):
    """Counts per classification category."""

    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int


class SampleGeneIds(CamelModel):
    """Sample gene IDs per classification category."""

    true_positives: list[str] = Field(default_factory=list)
    false_positives: list[str] = Field(default_factory=list)
    false_negatives: list[str] = Field(default_factory=list)
    true_negatives: list[str] = Field(default_factory=list)


class EvaluationSummaryResult(CamelModel):
    """Evaluation summary with metrics and sample genes."""

    metrics: ExperimentMetrics
    classification_counts: ClassificationCounts
    sample_gene_ids: SampleGeneIds
    status: ExperimentStatus


class EnrichmentResultsResponse(CamelModel):
    """Enrichment results from an experiment."""

    enrichment_results: list[EnrichmentResult] = Field(default_factory=list)
    count: int = 0


class ConfidenceScoresResult(CamelModel):
    """Cross-validation confidence scores."""

    cross_validation: CrossValidationResult


class ExperimentConfigResult(CamelModel):
    """Experiment configuration and status."""

    config: ExperimentConfig
    status: ExperimentStatus
    wdk_strategy_id: int | None = None
    wdk_step_id: int | None = None
    notes: str | None = None
    created_at: str = ""
    completed_at: str | None = None


class GeneListResult(CamelModel):
    """Gene list for a classification category."""

    classification: str
    genes: list[GeneInfo] = Field(default_factory=list)
    returned: int = 0
    total: int = 0
