"""Experiment and ExperimentConfig types."""

from assistant_core.platform.context import calling_application
from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat2
from pydantic import Field

from pathfinder.domain.parameters.values import ParamValue
from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.services.enrichment.types import (
    EnrichmentAnalysisType,
    EnrichmentResult,
)
from pathfinder.services.experiment.types.core import (
    ControlValueFormat,
    ExperimentMode,
    ExperimentStatus,
)
from pathfinder.services.experiment.types.metrics import (
    CrossValidationResult,
    ExperimentMetrics,
    GeneInfo,
)
from pathfinder.services.experiment.types.robustness import BootstrapResult


class ExperimentConfig(CamelModel):
    """Full configuration for an experiment run.

    Supports three modes:

    * **single** (default): one search + parameters.
    * **multi-step**: a recursive ``step_tree`` of search/combine/transform nodes.
    * **import**: import an existing Pathfinder strategy by ``source_strategy_id``.
    """

    site_id: str
    record_type: str
    search_name: str
    parameters: dict[str, ParamValue]
    positive_controls: list[str]
    negative_controls: list[str]
    controls_search_name: str
    controls_param_name: str
    controls_value_format: ControlValueFormat = "newline"
    enable_cross_validation: bool = False
    k_folds: int = 5
    enrichment_types: list[EnrichmentAnalysisType] = Field(default_factory=list)
    name: str = ""
    description: str = ""
    parameter_display_values: dict[str, str] | None = None
    mode: ExperimentMode = "single"
    step_tree: StrategyStepNode | None = None
    source_strategy_id: str | None = None
    control_set_id: str | None = None
    max_list_size: int | None = None
    parent_experiment_id: str | None = None
    target_gene_ids: list[str] | None = None

    @property
    def is_tree_mode(self) -> bool:
        """Whether this config uses a multi-step strategy tree."""
        return self.mode in ("multi-step", "import") and self.step_tree is not None


class BatchOrganismTarget(CamelModel):
    """Per-organism overrides for a cross-organism batch experiment."""

    organism: str
    positive_controls: list[str] | None = None
    negative_controls: list[str] | None = None


class BatchExperimentConfig(CamelModel):
    """Configuration for running the same search across multiple organisms."""

    base_config: ExperimentConfig
    organism_param_name: str
    target_organisms: list[BatchOrganismTarget] = Field(default_factory=list)


class Experiment(CamelModel):
    """Full experiment with config and results."""

    id: str
    config: ExperimentConfig
    user_id: str | None = None
    # The application the experiment was created under; it owns the experiment
    # with the user.
    application_id: str = Field(default_factory=calling_application)
    status: ExperimentStatus = "pending"
    metrics: ExperimentMetrics | None = None
    cross_validation: CrossValidationResult | None = None
    enrichment_results: list[EnrichmentResult] = Field(default_factory=list)
    true_positive_genes: list[GeneInfo] = Field(default_factory=list)
    false_negative_genes: list[GeneInfo] = Field(default_factory=list)
    false_positive_genes: list[GeneInfo] = Field(default_factory=list)
    true_negative_genes: list[GeneInfo] = Field(default_factory=list)
    error: str | None = None
    total_time_seconds: RoundedFloat2 | None = None
    created_at: str = ""
    completed_at: str | None = None
    batch_id: str | None = None
    benchmark_id: str | None = None
    control_set_label: str | None = None
    is_primary_benchmark: bool = False
    wdk_strategy_id: int | None = None
    wdk_step_id: int | None = None
    notes: str | None = None
    robustness: BootstrapResult | None = None

    def classification_id_sets(
        self,
    ) -> tuple[set[str], set[str], set[str], set[str]]:
        """Build classification ID sets from the gene lists.

        :returns: ``(tp_ids, fp_ids, fn_ids, tn_ids)``
        """
        return (
            {g.id for g in self.true_positive_genes},
            {g.id for g in self.false_positive_genes},
            {g.id for g in self.false_negative_genes},
            {g.id for g in self.true_negative_genes},
        )

    def result_gene_ids(self) -> set[str]:
        """Return the set of all result gene IDs (TP + FP)."""
        return {g.id for g in self.true_positive_genes} | {
            g.id for g in self.false_positive_genes
        }
