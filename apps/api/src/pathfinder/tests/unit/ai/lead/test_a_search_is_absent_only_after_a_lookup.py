"""A reply says a search is absent only when this turn looked the catalog up."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.reply_claims import says_a_search_is_absent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ABSENT = (
    "The product text search found 70 genes, but that search is not available "
    "in the current catalog."
)


def _asked(*, looked_up: bool) -> LeadDeps:
    state = pipeline_state(
        "amoebadb",
        user_prompt="Would a protein domain search find more genes than the text search?",
        user_message_id=uuid4(),
    )
    state.turn_markers.intent_classified = True
    state.turn_markers.catalog_looked_up = looked_up
    return lead_deps(state)


@pytest.mark.parametrize(
    "prose",
    [
        _ABSENT,
        "AmoebaDB has no search for InterPro domains.",
        "The InterPro domain search doesn't exist on this site.",
        "AmoebaDB does not offer a protein domain search.",
        "That search is unavailable here.",
        "There is no such search on AmoebaDB.",
    ],
)
def test_a_reply_that_says_a_search_is_absent_is_read_as_absence(prose: str) -> None:
    assert says_a_search_is_absent(prose) is True


@pytest.mark.parametrize(
    "prose",
    [
        "The step has 4 steps, count not available.",
        "The text search found 70 genes.",
        "No search step changed, and the strategy keeps its 1 gene.",
        "The domain search is not in this strategy, so I counted it on its own.",
    ],
)
def test_a_reply_that_says_no_absence_is_not_read_as_absence(prose: str) -> None:
    assert says_a_search_is_absent(prose) is False


def test_an_absence_with_no_lookup_is_refused_with_the_lookup_to_run() -> None:
    mismatches = reconcile(
        reply(_ABSENT), turn_record(run_context_for(_asked(looked_up=False)))
    )

    found = [m.sentence for m in mismatches if m.kind == "unbacked_absence"]
    assert found == [
        (
            "Your reply says a search is absent, and this turn looked nothing up "
            "in the catalog. Call count_search with the search's name: a name the "
            "catalog does not list comes back with the searches the catalog "
            "lookup finds, and a search is absent only when that lookup finds none."
        )
    ]


def test_an_absence_after_a_lookup_stands() -> None:
    assert "unbacked_absence" not in kinds(_asked(looked_up=True), reply(_ABSENT))


def test_a_membership_that_holds_no_gene_states_no_shared_count() -> None:
    assert (
        "When it holds none of them, say so, cite ``[compare:asked genes]`` and "
        "state no shared count."
    ) in " ".join(LEAD_INSTRUCTIONS.split())
