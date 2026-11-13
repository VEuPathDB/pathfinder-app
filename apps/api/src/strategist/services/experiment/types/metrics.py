"""Classification metrics for experiment runs."""

from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat
from pydantic import ConfigDict


class ConfusionMatrix(CamelModel):
    """2x2 confusion matrix counts."""

    model_config = ConfigDict(frozen=True)

    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


class ExperimentMetrics(CamelModel):
    """Full classification metrics derived from a confusion matrix."""

    model_config = ConfigDict(frozen=True)

    confusion_matrix: ConfusionMatrix
    sensitivity: RoundedFloat
    specificity: RoundedFloat
    precision: RoundedFloat
    f1_score: RoundedFloat
    mcc: RoundedFloat
    balanced_accuracy: RoundedFloat
    # Fields below may be absent in older persisted data.
    negative_predictive_value: RoundedFloat = 0.0
    false_positive_rate: RoundedFloat = 0.0
    false_negative_rate: RoundedFloat = 0.0
    youdens_j: RoundedFloat = 0.0
    total_results: int = 0
    total_positives: int = 0
    total_negatives: int = 0


class GeneInfo(CamelModel):
    """Minimal gene metadata."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str | None = None
    organism: str | None = None
    product: str | None = None
