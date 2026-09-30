"""The control-flow arcs play the calls their findings name."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.control_flow_arcs import (
    READ_AGAIN_RECORDS,
    REPEATED_CLASSIFICATIONS,
)
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests.unit.ai.models._mock_pins import framed_pins
from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play

SITES = ("plasmodb", "vectorbase")


@pytest.mark.parametrize("site_id", SITES)
def test_the_lead_sends_one_classification_again_then_answers(site_id: str) -> None:
    calls = play("lead", site_id, "Answer it [[arc:reclassified]]")

    assert names(calls) == [
        *["classify_user_intent"] * (REPEATED_CLASSIFICATIONS + 1),
        "final_result",
    ]


@pytest.mark.parametrize("site_id", SITES)
def test_the_lead_reads_each_record_twice_then_answers(site_id: str) -> None:
    calls = play("lead", site_id, "List them again [[arc:read-again]]")

    genes = list(
        SiteValues.for_site(site_id).controls.positive_ids[:READ_AGAIN_RECORDS]
    )
    assert names(calls) == [
        "classify_user_intent",
        *["read_gene_record"] * (2 * READ_AGAIN_RECORDS),
        "final_result",
    ]
    assert [a["gene_id"] for a in args_of(calls, "read_gene_record")] == genes * 2


@pytest.mark.parametrize("site_id", SITES)
def test_a_count_comparison_on_a_framed_thread_changes_no_step(site_id: str) -> None:
    calls = play(
        "lead",
        site_id,
        "How do the two counts compare? [[arc:count-comparison]]",
        scene=Scene(instructions=framed_pins()),
    )

    assert names(calls) == [
        "classify_user_intent",
        "compare_search_variants",
        "final_result",
    ]
    [intent] = args_of(calls, "classify_user_intent")
    assert intent["intent"]["classification"] == "follow_up_question"
    assert calls[-1].args_as_dict()["strategyChanged"] is False


_UNION_REFUSED = (
    "The structure is refused: a UNION joins step_signal, which the strategy "
    "holds, to c_membrane, which this turn adds, and the researcher stated no "
    "alternative that joins them."
)


@pytest.mark.parametrize("site_id", SITES)
def test_a_refused_union_ends_the_frame_pass_on_the_refusal(site_id: str) -> None:
    calls = play(
        "frame",
        site_id,
        "How does it compare? [[arc:union-refused]]",
        scene=Scene(refused={"set_structure": _UNION_REFUSED}),
    )

    assert names(calls)[-2:] == ["set_structure", "final_result"]
    assert _UNION_REFUSED in calls[-1].args_as_dict()["summary"]


@pytest.mark.parametrize("site_id", SITES)
def test_the_lead_answers_a_refused_union_with_the_comparison(site_id: str) -> None:
    calls = play(
        "lead",
        site_id,
        "How does it compare? [[arc:union-refused]]",
        scene=Scene(instructions=framed_pins()),
    )

    assert names(calls) == [
        "classify_user_intent",
        "edit_strategy",
        "compare_search_variants",
        "final_result",
    ]
    assert calls[-1].args_as_dict()["strategyChanged"] is False
