"""The comparison arc opens the study its message names, even when the
researcher's uploads are listed first."""

from __future__ import annotations

from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, play


def test_the_comparison_opens_the_study_the_message_names() -> None:
    listed = {
        "studies": [
            {"datasetId": "EDAUD_lhZ5ptRgo014J", "displayName": "pathfinder-uat-deseq"},
            {
                "datasetId": "DS_here",
                "displayName": "5 asexual and sexual stage transcriptomes",
            },
        ]
    }

    calls = play(
        "lead",
        "plasmodb",
        "5 asexual and sexual stage transcriptomes [[arc:eda-compare]]",
        scene=Scene(answers={"search_eda_studies": listed}),
    )

    assert args_of(calls, "open_eda_analysis")[0]["dataset_id"] == "DS_here"
