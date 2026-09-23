"""The compute's result names its groups and the sign of its effect size."""

from __future__ import annotations

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.jobs.impls.eda_compute_impl import compute_result
from pathfinder.services.eda.compute import RetainedSummary

PBM = EdaComparison(group_a=["24h pbm"], group_b=["18h pbm", "36h pbm"])
SUMMARY = RetainedSummary(
    total_rows=201, unparseable_rows=1, retained=67, retained_up=33, retained_down=34
)


def _result() -> dict[str, object]:
    return compute_result(
        job_id="job-1",
        status="complete",
        method="DESeq",
        effect_size_label="log2(Fold Change)",
        summary=SUMMARY,
        comparison=PBM,
    )


def test_the_result_carries_the_comparison() -> None:
    assert _result()["comparison"] == {
        "groupA": ["24h pbm"],
        "groupB": ["18h pbm", "36h pbm"],
    }


def test_the_result_states_the_sign_rule_by_group() -> None:
    assert _result()["signRule"] == (
        "A positive effect size means the gene is higher in group B "
        "(18h pbm, 36h pbm) than in group A (24h pbm)."
    )


def test_the_guidance_counts_each_side_by_its_group() -> None:
    guidance = _result()["guidance"]
    assert isinstance(guidance, str)
    assert "33 higher in 18h pbm, 36h pbm and 34 higher in 24h pbm" in guidance
    assert "upOnly keeps the 33, downOnly the 34" in guidance
