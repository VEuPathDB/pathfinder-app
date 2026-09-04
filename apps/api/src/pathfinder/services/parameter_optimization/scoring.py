"""Objective scoring for parameter sweeps."""

from pathfinder.services.parameter_optimization.config import OptimizationConfig

_DEFAULT_TOTAL_GENES = 20_000
"""The denominator used when the total gene count is unknown."""

_MCC_ZERO_GUARD_EPSILON = 1e-10
_MIN_COMPLETED_TRIALS = 2


def _score_mcc(r: float, specificity: float, raw_fpr: float) -> float:
    """Returns the Matthews correlation coefficient from the rate estimates."""
    tpr, tnr, fpr_val, fnr = r, specificity, raw_fpr, 1.0 - r
    num = tpr * tnr - fpr_val * fnr
    denom = ((tpr + fpr_val) * (tpr + fnr) * (tnr + fpr_val) * (tnr + fnr)) ** 0.5
    return (num / denom) if denom > _MCC_ZERO_GUARD_EPSILON else 0.0


def _score_for_objective(
    r: float,
    precision: float,
    specificity: float,
    raw_fpr: float,
    cfg: OptimizationConfig,
) -> float:
    """Returns the score for the configured objective, before any penalty."""
    f1_denom = precision + r
    fb_denom = cfg.beta**2 * precision + r
    scores: dict[str, float] = {
        "recall": r,
        "precision": precision,
        "specificity": specificity,
        "balanced_accuracy": (r + specificity) / 2.0,
        "mcc": _score_mcc(r, specificity, raw_fpr),
        "youdens_j": r + specificity - 1.0,
        "f1": (2 * precision * r / f1_denom) if f1_denom > 0 else 0.0,
        "f_beta": (
            ((1 + cfg.beta**2) * precision * r / fb_denom) if fb_denom > 0 else 0.0
        ),
        "custom": cfg.recall_weight * r - cfg.precision_weight * raw_fpr,
    }
    return scores.get(cfg.objective, r)


def _compute_score(
    recall: float | None,
    fpr: float | None,
    cfg: OptimizationConfig,
    *,
    estimated_size: int | None = None,
    positive_hits: int | None = None,
    negative_hits: int | None = None,
) -> float:
    r = recall if recall is not None else 0.0
    raw_fpr = fpr if fpr is not None else 0.0
    specificity = 1.0 - raw_fpr

    # Precision comes from the intersection counts. Specificity stands in for it when
    # those counts are absent.
    if positive_hits is not None and negative_hits is not None:
        tp_fp = positive_hits + negative_hits
        precision = positive_hits / tp_fp if tp_fp > 0 else 0.0
    else:
        precision = specificity

    base = _score_for_objective(r, precision, specificity, raw_fpr, cfg)

    # The result-count penalty breaks ties between large result sets.
    if (
        cfg.estimated_size_penalty > 0
        and estimated_size is not None
        and estimated_size > 0
    ):
        penalty = cfg.estimated_size_penalty * (estimated_size / _DEFAULT_TOTAL_GENES)
        base = max(base - penalty, 0.0)

    return base
