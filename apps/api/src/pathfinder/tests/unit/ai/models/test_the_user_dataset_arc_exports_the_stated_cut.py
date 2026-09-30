"""The user-dataset arc compares the upload's two conditions and exports at the
cut its message states."""

from __future__ import annotations

import pytest

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.services.eda.direction import caption_verdict
from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play

_MESSAGE = (
    "On my uploaded RNA-Seq dataset 'pathfinder-uat-deseq', run DESeq2 of treated "
    "against control and keep the up-regulated genes with log2 fold change > 5 "
    "and p-value < 1e-10. [[arc:user-dataset-deseq]]"
)
_UPLOAD = {"studies": [{"datasetId": "EDAUD_lhZ5ptRgo014J"}]}


@pytest.mark.parametrize("site_id", ["plasmodb", "vectorbase"])
def test_the_arc_exports_the_upload_at_the_stated_cut(site_id: str) -> None:
    calls = play(
        "lead", site_id, _MESSAGE, scene=Scene(answers={"search_eda_studies": _UPLOAD})
    )

    assert names(calls) == [
        "classify_user_intent",
        "search_eda_studies",
        "describe_eda_study",
        "describe_eda_study",
        "open_eda_analysis",
        "set_eda_filters",
        "set_eda_filters",
        "preview_eda_subset",
        "run_eda_compute",
        "create_eda_step",
        "verify_strategy",
        "final_result",
    ]
    (opened,) = args_of(calls, "open_eda_analysis")
    assert opened["dataset_id"] == "EDAUD_lhZ5ptRgo014J"
    (compute,) = args_of(calls, "run_eda_compute")
    compared = EdaComparison(
        group_a=compute["group_a_labels"], group_b=compute["group_b_labels"]
    )
    (exported,) = args_of(calls, "create_eda_step")
    caption = exported.pop("caption")
    assert exported == {
        "effect_size_threshold": 5.0,
        "significance_threshold": 1e-10,
        "effect_direction": "upOnly",
    }
    assert caption_verdict(caption, compared, "upOnly") == "agrees"
