"""Each id a listing returned links to the page of its step's record type."""

from __future__ import annotations

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.facts_reads import listed_ids
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.turn_facts import StepFact
from pathfinder.services.strategies.sync_state import WDKSyncState

_BLAST = StepFact(step_id="blast", display_name="BLAST", record_noun="sequence")
_GROUPS = StepFact(step_id="groups", display_name="Groups from sequences")


def test_a_protein_and_its_group_each_link_to_their_own_page() -> None:
    markers = TurnMarkers()
    markers.record_listed_genes(227256640, ["A0H76_3082-t39_1-p1"])
    markers.record_listed_genes(227256650, ["OG8_0001941"])
    sync = WDKSyncState(wdk_step_ids={"blast": 227256640, "groups": 227256650})

    listed = listed_ids(
        "orthomcl",
        markers,
        [_BLAST, _GROUPS],
        sync,
        [],
        {"blast": "sequence", "groups": "group"},
    )

    assert [fact.records for fact in listed] == [
        [
            ListedRecord(
                record_id="A0H76_3082-t39_1-p1",
                url="https://qa.orthomcl.org/orthomcl.qa/app/record/sequence/A0H76_3082-t39_1-p1",
            )
        ],
        [
            ListedRecord(
                record_id="OG8_0001941",
                url="https://qa.orthomcl.org/orthomcl.qa/app/record/group/OG8_0001941",
            )
        ],
    ]
