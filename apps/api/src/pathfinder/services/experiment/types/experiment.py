"""Experiment and ExperimentConfig types."""

from assistant_core.platform.context import calling_application
from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat2
from pydantic import Field
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.controls import ControlValueFormat

from pathfinder.services.experiment.types.core import ExperimentStatus
from pathfinder.services.experiment.types.metrics import ExperimentMetrics, GeneInfo


class ExperimentConfig(CamelModel):
    """One search with its parameters, scored against positive and negative controls."""

    site_id: str
    record_type: str
    search_name: str
    parameters: dict[str, ParamValue]
    positive_controls: list[str]
    negative_controls: list[str]
    controls_search_name: str
    controls_param_name: str
    controls_value_format: ControlValueFormat = "newline"
    name: str = ""


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
    true_positive_genes: list[GeneInfo] = Field(default_factory=list)
    false_negative_genes: list[GeneInfo] = Field(default_factory=list)
    false_positive_genes: list[GeneInfo] = Field(default_factory=list)
    true_negative_genes: list[GeneInfo] = Field(default_factory=list)
    error: str | None = None
    total_time_seconds: RoundedFloat2 | None = None
    created_at: str = ""
    completed_at: str | None = None

    def result_gene_ids(self) -> set[str]:
        """Return the set of all result gene IDs (TP + FP)."""
        return {g.id for g in self.true_positive_genes} | {
            g.id for g in self.false_positive_genes
        }
