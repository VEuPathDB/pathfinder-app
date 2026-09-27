"""An attached gene-id list with no token plays the attachment arc: the ids are
named as controls, saved as a control set, and the reply asks for negatives."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests.unit.ai.models._mock_turns import args_of, names, play

SITES = ("plasmodb", "vectorbase")


def _attached(site_id: str) -> str:
    ids = SiteValues.for_site(site_id).controls.positive_ids[:2]
    return f"Use these.\nAttached gene-ID list from controls.csv: {', '.join(ids)}"


@pytest.mark.parametrize("site_id", SITES)
def test_an_attached_list_with_no_token_saves_a_control_set(site_id: str) -> None:
    ids = SiteValues.for_site(site_id).controls.positive_ids[:2]

    calls = play("lead", site_id, _attached(site_id))

    assert names(calls) == ["classify_user_intent", "build_control_set", "final_result"]
    (classified,) = args_of(calls, "classify_user_intent")
    assert classified["intent"]["namedControls"] == {
        "positiveIds": ids,
        "negativeIds": [],
    }
    (saved,) = args_of(calls, "build_control_set")
    assert saved == {"name": "Controls from controls.csv", "positive_ids": ids}
    (final,) = args_of(calls, "final_result")
    assert final["askedQuestions"] == [
        {"question": "Which genes should I use as negative controls?"}
    ]
    assert final["prose"].endswith("Which genes should I use as negative controls?")
