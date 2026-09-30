"""The ids a listing of the turn returned are rows of its facts part, and the
numbers a reply may hold are the ones the facts count and the researcher wrote:
a number of a record's own words is held only beside that word."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.ai.lead.contract_messages import fact_outside_the_block_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests.unit.ai.lead.test_the_facts_hold_the_thread import (
    _joined_by_orthology,
    _leaf_read,
    _printed,
)

# The four Hammondia genes the orthology join dropped, as the two listings read them.
_DROPPED = ["HHA_208730", "HHA_208740", "HHA_218310", "HHA_247195"]
_DROPPED_REPLY = (
    "The four that dropped out are HHA_208730, HHA_208740, HHA_218310 and HHA_247195."
)


def _listed_after_the_join() -> LeadDeps:
    deps = _joined_by_orthology()
    ensure_sync_state(deps.runtime.strategy_session).wdk_step_ids = {
        "step_hha": 227295480,
        "step_join": 227295700,
    }
    deps.state.user_prompt = (
        "Which four of the original 23 Hammondia genes dropped out of the result?"
    )
    deps.state.turn_markers.record_listed_genes(227295480, [*_DROPPED, "HHA_204530"])
    deps.state.turn_markers.record_listed_genes(227295700, ["HHA_204530"])
    return deps


def test_the_ids_a_listing_returned_are_rows_under_their_step() -> None:
    facts = turn_facts(_listed_after_the_join())

    lines = facts.lines()
    listed = [line for line in lines if line.startswith("Listed from")]
    assert listed == [
        f"Listed from GenesByText: {', '.join([*_DROPPED, 'HHA_204530'])}",
        "Listed from Combine: HHA_204530",
    ]
    assert (lines.index(listed[0]), lines.index(listed[1])) == (1, 5)


def test_an_id_a_listing_returned_is_held_because_the_facts_show_it() -> None:
    assert _printed(_listed_after_the_join(), _DROPPED_REPLY) == []


def test_an_id_listed_from_a_step_the_strategy_no_longer_holds_is_refused() -> None:
    deps = _listed_after_the_join()
    ensure_sync_state(deps.runtime.strategy_session).wdk_step_ids = {
        "step_join": 227295700
    }

    assert _printed(deps, _DROPPED_REPLY) == [fact_outside_the_block_message(_DROPPED)]


def test_the_researchers_own_numbers_are_held() -> None:
    deps = _joined_by_orthology()
    deps.state.user_prompt = (
        "Cryptococcus neoformans H99 genes upregulated at 37 degrees compared "
        "with 30 degrees."
    )

    assert _printed(deps, "These 19 are higher at 37°C than at 30°C.") == []


@pytest.mark.parametrize(
    "prose",
    [
        "These are higher at 37°C than at 30°C.",
        "At p below 0.001 with a log2 fold change of 5 the step keeps 19 genes.",
        "The cut is log2 fold change 5 and p 0.001.",
    ],
)
def test_every_number_the_researcher_wrote_is_held(prose: str) -> None:
    deps = _joined_by_orthology()
    deps.state.user_prompt = (
        "Genes higher at 37 degrees than at 30 degrees, at p 0.001 and log2 fold "
        "change 5."
    )

    assert _printed(deps, prose) == []


def test_a_derived_number_is_refused_though_a_record_shows_its_digit() -> None:
    deps = _leaf_read()
    deps.state.turn_markers.record_read(
        ReadRecord(
            record_id="Tbg972.6.590",
            url="https://tritrypdb.org/tritrypdb/app/record/gene/Tbg972.6.590",
            product="hypothetical protein, conserved",
            organism="Trypanosoma brucei gambiense DAL972",
            chromosome="6",
        )
    )

    assert _printed(deps, "Tbg972.6.590 is on chromosome 6.") == []
    assert _printed(deps, "DAL972 has 6 more genes than TREU927.") == [
        fact_outside_the_block_message(["6"])
    ]


# The 19 Hammondia genes the check listed from the join, and the five of them
# no sampled record showed.
_JOINED = [
    "HHA_200230",
    "HHA_201780",
    "HHA_204530",
    "HHA_208030",
    "HHA_218520",
    "HHA_245485",
    "HHA_245490",
    "HHA_250710",
    "HHA_254430",
    "HHA_260190",
    "HHA_261780",
    "HHA_267680",
    "HHA_275798",
    "HHA_277080",
    "HHA_289630",
    "HHA_291890",
    "HHA_319560",
    "HHA_456270",
    "HHA_456770",
]
_UNSAMPLED = ["HHA_204530", "HHA_245485", "HHA_245490", "HHA_260190", "HHA_319560"]


def test_the_ids_the_join_listed_are_shown_and_the_reply_that_names_them_stands() -> (
    None
):
    deps = _joined_by_orthology()
    ensure_sync_state(deps.runtime.strategy_session).wdk_step_ids = {
        "step_join": 227295700
    }
    deps.state.turn_markers.record_listed_genes(227295700, _JOINED)

    facts = turn_facts(deps)
    [listed] = [line for line in facts.lines() if line.startswith("Listed from")]
    assert [g for g in _UNSAMPLED if g in listed.split(": ")[1].split(", ")] == (
        _UNSAMPLED
    )
    assert (
        [s.count_before for s in facts.steps if s.step_id == "c_me49"],
        facts.root_count_before,
    ) == ([None], 23)
    assert _printed(deps, f"It returns 19 genes: {', '.join(_JOINED)}.") == []


def test_each_listed_id_links_to_its_record_page() -> None:
    [listed, _] = turn_facts(_listed_after_the_join()).listed

    assert [(r.record_id, r.url) for r in listed.records[:2]] == [
        ("HHA_208730", "https://toxodb.org/toxo/app/record/gene/HHA_208730"),
        ("HHA_208740", "https://toxodb.org/toxo/app/record/gene/HHA_208740"),
    ]
