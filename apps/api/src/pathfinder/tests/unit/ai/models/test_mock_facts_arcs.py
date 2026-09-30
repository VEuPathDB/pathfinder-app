"""The listing arc names the ids its listing read, and the facts part shows each
of them under the step it listed, so the reply holds no id outside the facts."""

from __future__ import annotations

from pathfinder.ai.lead.facts_in_prose import outside_the_facts
from pathfinder.ai.models.mock.facts_arcs import LISTED
from pathfinder.domain.turn_facts import ListedFact, ListedRecord, StepFact, TurnFacts
from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play

# The first ids of the Hammondia microneme result, as the listing read them.
_IDS = ["HHA_204530", "HHA_245485", "HHA_245490", "HHA_260190", "HHA_319560"]


def test_the_listing_arc_names_the_ids_the_facts_list() -> None:
    calls = play(
        "lead",
        "toxodb",
        "Which genes are in the result? [[arc:list-ids]]",
        scene=Scene(
            answers={
                "read_step_ids": {
                    "wdkStepId": 227295700,
                    "geneIds": _IDS,
                    "total": 19,
                    "complete": False,
                }
            }
        ),
    )
    prose = str(calls[-1].args_as_dict()["prose"])
    facts = TurnFacts(
        steps=[StepFact(step_id="step_join", display_name="Intersect", count=19)],
        listed=[
            ListedFact(
                step_id="step_join",
                step_name="Intersect",
                records=[
                    ListedRecord(record_id=g, url=f"https://toxodb.org/{g}")
                    for g in _IDS
                ],
            )
        ],
    )

    assert names(calls) == ["classify_user_intent", "read_step_ids", "final_result"]
    assert args_of(calls, "read_step_ids") == [{"limit": LISTED}]
    assert (
        all(i in prose for i in _IDS),
        outside_the_facts(prose, "\n".join(facts.held_lines()), ()),
    ) == (True, [])
    assert outside_the_facts(prose, "Intersect: 19 genes", ()) == _IDS
