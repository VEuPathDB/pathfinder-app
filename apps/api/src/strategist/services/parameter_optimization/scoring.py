"""Objective scoring for parameter sweeps."""

from strategist.services.parameter_optimization.builders import TrialMetrics
from strategist.services.parameter_optimization.config import OptimizationConfig

_DEFAULT_TOTAL_GENES = 20_000
"""The denominator used when the total gene count is unknown."""

_MCC_ZERO_GUARD_EPSILON = 1e-10


def _score_mcc(r: float, specificity: float, raw_fpr: float) -> float:
    """Returns the Matthews correlation coefficient from the rate estimates."""
    tpr, tnr, fpr_val, fnr = r, specificity, raw_fpr, 1.0 - r
    num = tpr * tnr - fpr_val * fnr
    denom = ((tpr + fpr_val) * (tpr + fnr) * (tnr + fpr_val) * (tnr + fnr)) ** 0.5
    return (num / denom) if denom > _MCC_ZERO_GUARD_EPSILON else 0.0


def _ratio(num: float, denom: float) -> float:
    return num / denom if denom > 0 else 0.0


def _objective_scores(
    m: TrialMetrics, cfg: OptimizationConfig
) -> dict[str, float | None]:
    r, fpr, spec, precision = m.recall, m.fpr, m.specificity, m.precision
    scores: dict[str, float | None] = {
        "recall": r,
        "precision": precision,
        "specificity": spec,
    }
    if r is None:
        return scores
    if spec is not None and fpr is not None:
        scores |= {
            "balanced_accuracy": (r + spec) / 2.0,
            "mcc": _score_mcc(r, spec, fpr),
            "youdens_j": r + spec - 1.0,
            "custom": cfg.recall_weight * r - cfg.precision_weight * fpr,
        }
    if precision is not None:
        scores |= {
            "f1": _ratio(2 * precision * r, precision + r),
            "f_beta": _ratio(
                (1 + cfg.beta**2) * precision * r, cfg.beta**2 * precision + r
            ),
        }
    return scores


def _compute_score(
    m: TrialMetrics, cfg: OptimizationConfig, *, estimated_size: int | None = None
) -> float | None:
    """The objective's score, or recall when the controls do not measure the
    objective; None when no positive control was measured."""
    measured = _objective_scores(m, cfg).get(cfg.objective)
    base = m.recall if measured is None else measured
    if base is None:
        return None
    # The result-count penalty breaks ties between large result sets.
    if (
        cfg.estimated_size_penalty > 0
        and estimated_size is not None
        and estimated_size > 0
    ):
        penalty = cfg.estimated_size_penalty * (estimated_size / _DEFAULT_TOTAL_GENES)
        base = max(base - penalty, 0.0)
    return base
