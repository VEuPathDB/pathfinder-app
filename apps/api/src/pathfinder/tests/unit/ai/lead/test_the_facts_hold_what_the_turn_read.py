"""The ids a listing of the turn returned are rows of its facts part, and a
reply names each listed id by a reference to its record."""

from __future__ import annotations

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.reply_references import ProseFault
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests.unit.ai.lead.test_the_facts_hold_the_thread import (
    _faults,
    _joined_by_orthology,
    _rendered,
)

# The four Hammondia genes the orthology join dropped, as the two listings read them.
_DROPPED = ["HHA_208730", "HHA_208740", "HHA_218310", "HHA_247195"]
_DROPPED_REPLY = (
    "The four that dropped out are [record:HHA_208730], [record:HHA_208740], "
    "[record:HHA_218310] and [record:HHA_247195]."
)
_TOXO_RECORD = "https://toxodb.org/toxo/app/record/gene/"


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


def test_an_id_a_listing_returned_renders_linked_to_its_record() -> None:
    assert _rendered(_listed_after_the_join(), _DROPPED_REPLY) == (
        f"The four that dropped out are [HHA_208730]({_TOXO_RECORD}HHA_208730), "
        f"[HHA_208740]({_TOXO_RECORD}HHA_208740), "
        f"[HHA_218310]({_TOXO_RECORD}HHA_218310) and "
        f"[HHA_247195]({_TOXO_RECORD}HHA_247195)."
    )


def test_an_id_listed_from_a_step_the_strategy_no_longer_holds_is_unheld() -> None:
    deps = _listed_after_the_join()
    ensure_sync_state(deps.runtime.strategy_session).wdk_step_ids = {
        "step_join": 227295700
    }

    assert _faults(deps, _DROPPED_REPLY) == [
        ProseFault(token=f"[record:{gene}]", kind="unheld_reference")
        for gene in _DROPPED
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
    listing = ", ".join(f"[record:{gene}]" for gene in _JOINED)
    assert _faults(deps, f"It returns [root]: {listing}.") == []


def test_each_listed_id_links_to_its_record_page() -> None:
    [listed, _] = turn_facts(_listed_after_the_join()).listed

    assert [(r.record_id, r.url) for r in listed.records[:2]] == [
        ("HHA_208730", "https://toxodb.org/toxo/app/record/gene/HHA_208730"),
        ("HHA_208740", "https://toxodb.org/toxo/app/record/gene/HHA_208740"),
    ]
