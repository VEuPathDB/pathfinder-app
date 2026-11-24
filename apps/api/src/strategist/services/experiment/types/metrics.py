"""Classification metrics for experiment runs."""

from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat
from pydantic import ConfigDict

from strategist.domain.unread import Unread

type Measured = RoundedFloat | Unread

NOT_STORED = Unread(reason="not stored with this run")


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
    sensitivity: Measured
    specificity: Measured
    precision: Measured
    f1_score: Measured
    mcc: Measured
    balanced_accuracy: Measured
    negative_predictive_value: Measured = NOT_STORED
    false_positive_rate: Measured = NOT_STORED
    false_negative_rate: Measured = NOT_STORED
    youdens_j: Measured = NOT_STORED
    total_positives: int = 0
    total_negatives: int = 0


class GeneInfo(CamelModel):
    """Minimal gene metadata."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str | None = None
    organism: str | None = None
    product: str | None = None
