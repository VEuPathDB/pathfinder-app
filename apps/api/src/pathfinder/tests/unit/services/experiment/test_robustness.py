"""Bootstrap robustness — the verification step every journey runs. It's pure
and seeded, so the confidence intervals are exactly reproducible. We pin
hand-reasoned degenerate cases (perfect / zero recovery), the reproducibility
guarantee the thesis depends on, and the CI invariants.
"""

from __future__ import annotations

from pathfinder.services.experiment.robustness import (
    BootstrapOptions,
    compute_robustness,
)

_FAST = BootstrapOptions(n_bootstrap=60, seed=42)


def test_perfect_separation_yields_unit_confidence_intervals() -> None:
    # All positives are in the result, no negatives are → every bootstrap
    # resample scores sensitivity=specificity=precision=F1=1.0.
    result = ["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0300300"]
    res = compute_robustness(
        result_ids=result,
        positive_ids=["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0300300"],
        negative_ids=["PF3D7_0930300", "PF3D7_1133400"],
        options=_FAST,
    )
    for metric in ("sensitivity", "specificity", "precision", "f1_score"):
        ci = res.metric_cis[metric]
        assert ci.lower == 1.0
        assert ci.upper == 1.0
        assert ci.mean == 1.0
        assert ci.std == 0.0


def test_zero_recovery_yields_zero_sensitivity() -> None:
    # No positive is in the result → sensitivity is 0 across all resamples;
    # no negative is in the result → specificity stays 1.0.
    res = compute_robustness(
        result_ids=["PF3D7_9999999"],
        positive_ids=["PF3D7_0100100", "PF3D7_0200200"],
        negative_ids=["PF3D7_0930300", "PF3D7_1133400"],
        options=_FAST,
    )
    assert res.metric_cis["sensitivity"].lower == 0.0
    assert res.metric_cis["sensitivity"].upper == 0.0
    assert res.metric_cis["specificity"].lower == 1.0


def test_is_reproducible_for_a_fixed_seed() -> None:
    # A partially-recovered set produces non-degenerate CIs; the same seed must
    # reproduce them exactly (reproducible thesis numbers).
    kwargs = {
        "result_ids": ["g1", "g2", "g3", "g4", "g5"],
        "positive_ids": ["g1", "g2", "p3", "p4"],  # only 2 of 4 recovered
        "negative_ids": ["g5", "n2", "n3"],  # 1 of 3 falsely recovered
    }
    a = compute_robustness(**kwargs, options=BootstrapOptions(n_bootstrap=80, seed=42))
    b = compute_robustness(**kwargs, options=BootstrapOptions(n_bootstrap=80, seed=42))
    assert a.metric_cis["sensitivity"].mean == b.metric_cis["sensitivity"].mean
    assert a.metric_cis["f1_score"].lower == b.metric_cis["f1_score"].lower
    assert a.metric_cis["f1_score"].upper == b.metric_cis["f1_score"].upper


def test_ci_bounds_are_ordered_and_in_range() -> None:
    res = compute_robustness(
        result_ids=["g1", "g2", "g3", "g4", "g5"],
        positive_ids=["g1", "g2", "p3", "p4"],
        negative_ids=["g5", "n2", "n3"],
        options=BootstrapOptions(n_bootstrap=80, seed=42),
    )
    for ci in res.metric_cis.values():
        assert 0.0 <= ci.lower <= ci.mean <= ci.upper <= 1.0
        assert ci.std >= 0.0
    # A partial-recovery sensitivity (2/4 base) sits strictly between 0 and 1.
    assert 0.0 < res.metric_cis["sensitivity"].mean < 1.0
