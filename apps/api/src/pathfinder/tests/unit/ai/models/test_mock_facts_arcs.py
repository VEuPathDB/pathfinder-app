"""The listing arc names each id its listing read by a reference to its
record, which renders from the listing the facts part shows under its step."""

from __future__ import annotations

from pathfinder.ai.models.mock.facts_arcs import LISTED
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.reply_references import (
    ProseFault,
    prose_faults,
    render_reply,
)
from pathfinder.domain.turn_facts import ListedFact, StepFact, TurnFacts
from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play

# The first ids of the Hammondia microneme result, as the listing read them.
_IDS = ["HHA_204530", "HHA_245485", "HHA_245490", "HHA_260190", "HHA_319560"]
_PAGE = "https://toxodb.org/toxo/app/record/gene/"


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
    step = StepFact(step_id="step_join", display_name="Intersect", count=19)
    facts = TurnFacts(
        steps=[step],
        listed=[
            ListedFact(
                step_id="step_join",
                step_name="Intersect",
                records=[ListedRecord(record_id=g, url=f"{_PAGE}{g}") for g in _IDS],
            )
        ],
    )

    assert names(calls) == ["classify_user_intent", "read_step_ids", "final_result"]
    assert args_of(calls, "read_step_ids") == [{"limit": LISTED}]
    assert render_reply(prose, facts) == (
        f"The result starts with {', '.join(f'[{g}]({_PAGE}{g})' for g in _IDS)}."
    )
    assert prose_faults(prose, TurnFacts(steps=[step])) == [
        ProseFault(token=f"[record:{g}]", kind="unheld_reference") for g in _IDS
    ]
