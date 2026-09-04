"""Experiment Lab request/response DTOs."""

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import Field, JsonValue

from pathfinder.domain.parameters.values import ParamValue
from pathfinder.services.experiment.types import (
    ControlValueFormat,
    EnrichmentAnalysisType,
    ExperimentMode,
)
from pathfinder.transport.http.schemas.site_id import SiteId


class CreateExperimentRequest(CamelModel):
    """Request to create and run an experiment.

    Supports three modes: ``single`` (default), ``multi-step``, and ``import``.
    """

    site_id: SiteId
    record_type: str
    mode: ExperimentMode = Field(default="single")
    search_name: str = Field(default="")
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    step_tree: JsonValue = Field(default=None)
    source_strategy_id: str | None = Field(default=None)
    positive_controls: list[str]
    negative_controls: list[str]
    controls_search_name: str
    controls_param_name: str
    controls_value_format: ControlValueFormat = Field(default="newline")
    enable_cross_validation: bool = Field(default=False)
    k_folds: int = Field(default=5, ge=2, le=10)
    enrichment_types: list[EnrichmentAnalysisType] = Field(default_factory=list)
    name: str = Field(default="Untitled Experiment", max_length=200)
    description: str = Field(default="", max_length=2000)
    parameter_display_values: JSONObject | None = Field(default=None)
    control_set_id: str | None = Field(default=None)
    max_list_size: int | None = Field(default=None)
    parent_experiment_id: str | None = Field(default=None)
    target_gene_ids: list[str] | None = Field(default=None)


class BatchOrganismTargetRequest(CamelModel):
    """Per-organism override for a cross-organism batch experiment."""

    organism: str
    positive_controls: list[str] | None = Field(default=None)
    negative_controls: list[str] | None = Field(default=None)


class CreateBatchExperimentRequest(CamelModel):
    """Request to run the same search across multiple organisms."""

    base: CreateExperimentRequest
    organism_param_name: str
    target_organisms: list[BatchOrganismTargetRequest] = Field(min_length=1)


class ThresholdSweepRequest(CamelModel):
    """Request to sweep a parameter across a range (numeric) or set of values (categorical)."""

    parameter_name: str
    sweep_type: Literal["numeric", "categorical"] = Field(default="numeric")
    min: float | None = None
    max: float | None = None
    steps: int = Field(default=10, ge=3, le=50)
    values: list[str] | None = Field(default=None)


class CustomEnrichRequest(CamelModel):
    """Request to run a custom gene-set enrichment test."""

    gene_set_name: str = Field(min_length=1)
    gene_ids: list[str] = Field(min_length=1)


class BenchmarkControlSet(CamelModel):
    """A single control set within a benchmark suite."""

    label: str = Field(min_length=1)
    positive_controls: list[str]
    negative_controls: list[str]
    control_set_id: str | None = Field(default=None)
    is_primary: bool = Field(default=False)


class CreateBenchmarkRequest(CamelModel):
    """Request to run a benchmark suite across multiple control sets."""

    base: CreateExperimentRequest
    control_sets: list[BenchmarkControlSet] = Field(min_length=1)
