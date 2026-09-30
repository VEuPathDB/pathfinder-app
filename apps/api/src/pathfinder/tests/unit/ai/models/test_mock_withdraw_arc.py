"""The withdraw arc: the card offers to drop a requirement no search states,
and the answered card builds the rest."""

from __future__ import annotations

import pytest

from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play
from pathfinder.tests.unit.ai.models.test_mock_lead_arcs import BUILD, FRAMED, SITES

_DROP_QUESTION = "No search on this site states '2-fold'. Drop it from the request?"


def _withdrawing_frame() -> dict[str, object]:
    """A pass that bound the signal peptide step; the dispatch added the card
    that offers to drop the fold change no search of it states."""
    return {
        "summary": "Framed 1 criterion(s).",
        "disposition": "spec_ready",
        "openQuestions": [],
        "cardQuestions": [
            {
                "id": "q1",
                "prompt": _DROP_QUESTION,
                "dimension": "fold_change",
                "options": [
                    {"label": "Drop 2-fold", "recommended": False},
                    {"label": "Keep 2-fold", "recommended": False},
                ],
            }
        ],
    }


@pytest.mark.parametrize("site_id", SITES)
def test_a_requirement_no_search_states_is_offered_for_withdrawal(
    site_id: str,
) -> None:
    scene = Scene(answers={"frame_problem": _withdrawing_frame()})

    calls = play(
        "lead", site_id, "Up at least 2-fold, please [[arc:withdraw]]", scene=scene
    )

    classified = args_of(calls, "classify_user_intent")[0]
    [card] = args_of(calls, "consult_user")
    assert names(calls) == [*FRAMED[:2], "consult_user", *BUILD]
    assert classified["intent"]["explicitConstraints"] == [
        {
            "kind": "fold_change",
            "label": "fold change",
            "requestedValue": "2-fold",
            "source": "user_explicit",
            "hard": True,
        }
    ]
    assert [
        (q["prompt"], [o["label"] for o in q["options"]]) for q in card["questions"]
    ] == [(_DROP_QUESTION, ["Drop 2-fold", "Keep 2-fold"])]
