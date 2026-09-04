"""Bootstrap robustness estimation. Pure computation, with no WDK calls."""

import random
from collections import defaultdict
from dataclasses import dataclass

from assistant_core.platform.logging import get_logger

from pathfinder.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
)
from pathfinder.services.experiment.types import (
    BootstrapResult,
    ConfidenceInterval,
)

logger = get_logger(__name__)


class _SeededRNG(random.Random):
    """Deterministic PRNG for statistical sampling (not security use)."""


@dataclass
class BootstrapOptions:
    """Options for bootstrap robustness computation."""

    n_bootstrap: int = 200
    seed: int = 42


def compute_robustness(
    result_ids: list[str],
    positive_ids: list[str],
    negative_ids: list[str],
    options: BootstrapOptions | None = None,
) -> BootstrapResult:
    """Compute bootstrap confidence intervals for the classification metrics."""
    opts = options or BootstrapOptions()

    rng = _SeededRNG(opts.seed)

    metric_samples: dict[str, list[float]] = defaultdict(list)

    pos_list = list(positive_ids)
    neg_list = list(negative_ids)

    for _ in range(opts.n_bootstrap):
        boot_pos = _resample(pos_list, rng)
        boot_neg = _resample(neg_list, rng)

        _collect_classification_metrics(
            result_ids, set(boot_pos), set(boot_neg), metric_samples
        )

    return BootstrapResult(
        n_iterations=opts.n_bootstrap,
        metric_cis={k: _ci_from_samples(v) for k, v in metric_samples.items()},
    )


def _resample(items: list[str], rng: random.Random) -> list[str]:
    """Resample with replacement."""
    n = len(items)
    if n == 0:
        return []
    return [items[rng.randint(0, n - 1)] for _ in range(n)]


def _collect_classification_metrics(
    result_ids: list[str],
    pos_set: set[str],
    neg_set: set[str],
    samples: dict[str, list[float]],
) -> None:
    """Compute binary classification metrics and accumulate into samples dict."""
    result_set = set(result_ids)
    cm = compute_confusion_matrix(
        positive_hits=len(pos_set & result_set),
        total_positives=len(pos_set),
        negative_hits=len(neg_set & result_set),
        total_negatives=len(neg_set),
    )
    m = compute_metrics(cm)

    samples["sensitivity"].append(m.sensitivity)
    samples["specificity"].append(m.specificity)
    samples["precision"].append(m.precision)
    samples["f1_score"].append(m.f1_score)


def _ci_from_samples(
    samples: list[float],
    alpha: float = 0.05,
) -> ConfidenceInterval:
    """Compute percentile-based confidence interval."""
    if not samples:
        return ConfidenceInterval(lower=0.0, mean=0.0, upper=0.0, std=0.0)
    n = len(samples)
    sorted_s = sorted(samples)
    lo_idx = max(0, int(n * alpha / 2))
    hi_idx = min(n - 1, int(n * (1 - alpha / 2)))
    mean = sum(sorted_s) / n
    variance = sum((x - mean) ** 2 for x in sorted_s) / max(n - 1, 1)
    std = variance**0.5
    return ConfidenceInterval(
        lower=sorted_s[lo_idx],
        mean=mean,
        upper=sorted_s[hi_idx],
        std=std,
    )
