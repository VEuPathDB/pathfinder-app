"""K-fold cross-validation over positive and negative control gene lists."""

import math
import operator
import random
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from typing import Any

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb_mcp.controls import (
    ControlsContext,
    ControlTestResult,
    IntersectionConfig,
    run_positive_negative_controls,
)

from pathfinder.platform.identity import CONTROL_TEST_STRATEGY_NAME
from pathfinder.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
    metrics_from_control_result,
)
from pathfinder.services.experiment.tree_evaluation import (
    run_controls_against_tree,
)
from pathfinder.services.experiment.types import (
    ConfusionMatrix,
    CrossValidationResult,
    ExperimentMetrics,
    FoldMetrics,
)

logger = get_logger(__name__)

_MIN_FOLDS_FOR_STD = 2
_OVERFITTING_LOW_THRESHOLD = 0.1
_OVERFITTING_MODERATE_THRESHOLD = 0.25
_MIN_CONTROLS_FOR_FOLD = 2

ProgressCallback = Callable[[int, int], Coroutine[Any, Any, None]]
"""Async callback(fold_index, total_folds) for progress reporting."""


@dataclass
class CrossValidationOptions:
    """Options for k-fold cross-validation."""

    k: int = 5
    full_metrics: ExperimentMetrics | None = None
    progress_callback: ProgressCallback | None = field(default=None, compare=False)


class _SeededRNG(random.Random):
    """Deterministic PRNG for statistical shuffling (not security use)."""


def _stratified_kfold(ids: list[str], k: int, seed: int = 42) -> list[list[str]]:
    """Split a list into k roughly equal folds (deterministic)."""
    shuffled = list(ids)
    rng = _SeededRNG(seed)
    rng.shuffle(shuffled)
    folds: list[list[str]] = [[] for _ in range(k)]
    for i, item in enumerate(shuffled):
        folds[i % k].append(item)
    return folds


def _average_metrics(fold_metrics_list: list[ExperimentMetrics]) -> ExperimentMetrics:
    """Compute element-wise mean of a list of metrics."""
    n = len(fold_metrics_list)
    if n == 0:
        cm = ConfusionMatrix(
            true_positives=0,
            false_positives=0,
            true_negatives=0,
            false_negatives=0,
        )
        return compute_metrics(cm)

    def _mean(getter: Callable[[ExperimentMetrics], float]) -> float:
        return sum(getter(m) for m in fold_metrics_list) / n

    cm = ConfusionMatrix(
        true_positives=round(_mean(lambda m: m.confusion_matrix.true_positives)),
        false_positives=round(_mean(lambda m: m.confusion_matrix.false_positives)),
        true_negatives=round(_mean(lambda m: m.confusion_matrix.true_negatives)),
        false_negatives=round(_mean(lambda m: m.confusion_matrix.false_negatives)),
    )

    return ExperimentMetrics(
        confusion_matrix=cm,
        sensitivity=_mean(lambda m: m.sensitivity),
        specificity=_mean(lambda m: m.specificity),
        precision=_mean(lambda m: m.precision),
        negative_predictive_value=_mean(lambda m: m.negative_predictive_value),
        false_positive_rate=_mean(lambda m: m.false_positive_rate),
        false_negative_rate=_mean(lambda m: m.false_negative_rate),
        f1_score=_mean(lambda m: m.f1_score),
        mcc=_mean(lambda m: m.mcc),
        balanced_accuracy=_mean(lambda m: m.balanced_accuracy),
        youdens_j=_mean(lambda m: m.youdens_j),
        total_results=round(_mean(lambda m: m.total_results)),
        total_positives=round(_mean(lambda m: m.total_positives)),
        total_negatives=round(_mean(lambda m: m.total_negatives)),
    )


def _std_metrics(
    fold_metrics_list: list[ExperimentMetrics],
    mean: ExperimentMetrics,
) -> dict[str, float]:
    """Compute std deviation for key metrics across folds."""
    n = len(fold_metrics_list)
    if n < _MIN_FOLDS_FOR_STD:
        return {}

    fields: list[tuple[str, Callable[[ExperimentMetrics], float]]] = [
        ("sensitivity", operator.attrgetter("sensitivity")),
        ("specificity", operator.attrgetter("specificity")),
        ("precision", operator.attrgetter("precision")),
        ("f1Score", operator.attrgetter("f1_score")),
        ("mcc", operator.attrgetter("mcc")),
        ("balancedAccuracy", operator.attrgetter("balanced_accuracy")),
    ]

    result: dict[str, float] = {}
    for name, getter in fields:
        mean_val = getter(mean)
        variance = sum((getter(m) - mean_val) ** 2 for m in fold_metrics_list) / (n - 1)
        result[name] = math.sqrt(variance)
    return result


def _compute_overfitting_score(
    full_metrics: ExperimentMetrics,
    mean_holdout: ExperimentMetrics,
) -> tuple[float, str]:
    """Estimate overfitting from the gap between full-set and holdout metrics.

    :returns: (score, level) where score is 0-1 and level is low/moderate/high.
    """
    f1_gap = abs(full_metrics.f1_score - mean_holdout.f1_score)
    sens_gap = abs(full_metrics.sensitivity - mean_holdout.sensitivity)
    spec_gap = abs(full_metrics.specificity - mean_holdout.specificity)

    score = (f1_gap + sens_gap + spec_gap) / 3.0

    if score < _OVERFITTING_LOW_THRESHOLD:
        level = "low"
    elif score < _OVERFITTING_MODERATE_THRESHOLD:
        level = "moderate"
    else:
        level = "high"
    return score, level


FoldEvaluator = Callable[
    [list[str] | None, list[str] | None],
    Coroutine[Any, Any, ControlTestResult],
]
"""Async callback(holdout_pos, holdout_neg) -> control-test result."""


async def _run_kfold(
    *,
    positive_controls: list[str],
    negative_controls: list[str],
    evaluator: FoldEvaluator,
    k: int = 5,
    full_metrics: ExperimentMetrics | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CrossValidationResult:
    """Shared k-fold cross-validation loop.

    :param evaluator: Async callable that evaluates one fold's held-out controls.
    :param k: Number of folds.
    :param full_metrics: Pre-computed full-set metrics (for overfitting comparison).
    :param progress_callback: Optional progress reporter.
    :returns: Cross-validation result with per-fold and aggregate metrics.
    """
    # k must be at most the size of the smallest non-empty control set,
    # but at least 2.  If either set has fewer than 2 items, skip it
    # in the min() so we can still cross-validate the other set.
    size_caps = [
        len(s)
        for s in (positive_controls, negative_controls)
        if len(s) >= _MIN_CONTROLS_FOR_FOLD
    ]
    k = (
        max(_MIN_CONTROLS_FOR_FOLD, min(k, *size_caps))
        if size_caps
        else _MIN_CONTROLS_FOR_FOLD
    )

    pos_folds = _stratified_kfold(positive_controls, k)
    neg_folds = _stratified_kfold(negative_controls, k)

    fold_results: list[FoldMetrics] = []

    for fold_idx in range(k):
        holdout_pos = pos_folds[fold_idx]
        holdout_neg = neg_folds[fold_idx]

        if progress_callback:
            await progress_callback(fold_idx, k)

        try:
            result = await evaluator(
                holdout_pos or None,
                holdout_neg or None,
            )
            fold_metrics = metrics_from_control_result(result)
        except VEuPathDBError as exc:
            logger.warning("Fold %d failed: %s", fold_idx, exc)
            cm = compute_confusion_matrix(
                positive_hits=0,
                total_positives=len(holdout_pos),
                negative_hits=0,
                total_negatives=len(holdout_neg),
            )
            fold_metrics = compute_metrics(cm)

        fold_results.append(
            FoldMetrics(
                fold_index=fold_idx,
                metrics=fold_metrics,
                positive_control_ids=holdout_pos,
                negative_control_ids=holdout_neg,
            )
        )

    metrics_list = [f.metrics for f in fold_results]
    mean = _average_metrics(metrics_list)
    std = _std_metrics(metrics_list, mean)

    if full_metrics is not None:
        ov_score, ov_level = _compute_overfitting_score(full_metrics, mean)
    else:
        ov_score, ov_level = 0.0, "low"

    return CrossValidationResult(
        k=k,
        folds=fold_results,
        mean_metrics=mean,
        std_metrics=std,
        overfitting_score=ov_score,
        overfitting_level=ov_level,
    )


async def run_cross_validation(
    ctx: ControlsContext,
    tree: StrategyStepNode | None,
    search_name: str | None,
    parameters: dict[str, ParamValue] | None,
    options: CrossValidationOptions | None = None,
) -> CrossValidationResult:
    """Run k-fold cross-validation on control gene lists.

    When *tree* is provided, evaluates each fold against the full strategy
    tree.  Otherwise, evaluates using the single-step *search_name* +
    *parameters*.

    :param ctx: Shared controls context (site, record type, controls config,
        positive/negative controls).
    :param tree: Strategy plan tree for tree-mode evaluation, or ``None`` for
        single-step mode.
    :param search_name: WDK search name (single-step mode only).
    :param parameters: WDK search parameters (single-step mode only).
    :param options: Cross-validation options (k, full_metrics, progress_callback).
    """
    opts = options or CrossValidationOptions()
    evaluator: FoldEvaluator

    if tree is not None:

        async def _evaluate_tree(
            pos: list[str] | None, neg: list[str] | None
        ) -> ControlTestResult:
            fold_ctx = replace(
                ctx,
                positive_controls=pos or [],
                negative_controls=neg or [],
            )
            return await run_controls_against_tree(fold_ctx, tree)

        evaluator = _evaluate_tree
    else:
        if search_name is None or parameters is None:
            msg = "search_name and parameters are required for single-step cross-validation"
            raise ValidationError(detail=msg)
        # Bind to locals so the closure captures the non-None values.
        _search_name = search_name
        _parameters = parameters

        _intersection_cfg = IntersectionConfig.from_controls_context(
            ctx,
            target_search_name=_search_name,
            target_parameters=_parameters,
            internal_strategy_name=CONTROL_TEST_STRATEGY_NAME,
        )

        async def _evaluate_single(
            pos: list[str] | None, neg: list[str] | None
        ) -> ControlTestResult:
            return await run_positive_negative_controls(
                _intersection_cfg,
                positive_controls=pos,
                negative_controls=neg,
            )

        evaluator = _evaluate_single

    return await _run_kfold(
        positive_controls=ctx.positive_controls,
        negative_controls=ctx.negative_controls,
        evaluator=evaluator,
        k=opts.k,
        full_metrics=opts.full_metrics,
        progress_callback=opts.progress_callback,
    )
