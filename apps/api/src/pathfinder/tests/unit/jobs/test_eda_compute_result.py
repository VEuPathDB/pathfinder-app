"""The compute's result names its groups, the sign of its effect size and the
default cut it was counted at."""

from __future__ import annotations

from pydantic import JsonValue

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.jobs.impls.eda_compute_impl import compute_result
from pathfinder.services.eda.compute import RetainedSummary

PBM = EdaComparison(group_a=["24h pbm"], group_b=["18h pbm", "36h pbm"])
SUMMARY = RetainedSummary(
    total_rows=201, unparseable_rows=1, retained=67, retained_up=33, retained_down=34
)


def _result() -> dict[str, JsonValue]:
    return compute_result(
        job_id="job-1",
        status="complete",
        method="DESeq",
        effect_size_label="log2(Fold Change)",
        summary=SUMMARY,
        comparison=PBM,
    ).model_dump(by_alias=True, mode="json")


def test_the_result_is_the_summary_the_agent_resumes_with() -> None:
    assert _result() == {
        "jobId": "job-1",
        "status": "complete",
        "computeName": "differentialexpression",
        "method": "DESeq",
        "effectSizeLabel": "log2(Fold Change)",
        "genesTested": 201,
        "genesUnreadable": 1,
        "effectSizeThreshold": 1.0,
        "significanceThreshold": 0.05,
        "retained": 67,
        "retainedUp": 33,
        "retainedDown": 34,
        "comparison": {"groupA": ["24h pbm"], "groupB": ["18h pbm", "36h pbm"]},
        "signRule": (
            "A positive effect size means the gene is higher in group B "
            "(18h pbm, 36h pbm) than in group A (24h pbm)."
        ),
        "guidance": (
            "67 of 201 genes pass an effect size of 1.0 and a p-value of 0.05: "
            "33 higher in 18h pbm, 36h pbm and 34 higher in 24h pbm. upOnly keeps "
            "the 33, downOnly the 34. Call create_eda_step with those thresholds "
            "to export them, or with different ones to change the cut."
        ),
    }
