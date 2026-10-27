"""Each fault makes its wrong call in place of the arc's, once a turn. The arc
makes the right call once the refusal is back, or keeps a corrected call as its own."""

from __future__ import annotations

from pydantic_ai.messages import (
    ToolCallPart,
)

from pathfinder.ai.models.mock import fault_calls
from pathfinder.ai.models.mock.faults import FAULTS, made_by_a_fault
from pathfinder.tests.unit.ai.models._mock_questions import asking_frame
from pathfinder.tests.unit.ai.models._mock_turns import (
    CONTROL_SET_ID,
    LIVE_ROOT_COUNT,
    STRATEGY_ROOT_WDK_ID,
    Scene,
    args_of,
    names,
    play,
    verify_order,
)

_FRAME_ORDER = "Frame work order: mock frame"
_REFUSED = "refused by the guard"
_SITE = "plasmodb"
_ORGANISM = "Plasmodium falciparum 3D7"


def _token(arc: str, fault: str) -> str:
    return f"[[arc:{arc}]][[fault:{fault}]]"


def _faulted(calls: list[ToolCallPart]) -> list[ToolCallPart]:
    return [call for call in calls if made_by_a_fault(call)]


def _refusing(tool: str) -> Scene:
    return Scene(faulted={tool: _REFUSED})


def _frame(arc: str, fault: str, work_order: str = _FRAME_ORDER) -> list[ToolCallPart]:
    return play(
        "frame",
        _SITE,
        _token(arc, fault),
        work_order=work_order,
        scene=_refusing("set_criterion"),
    )


def _lead(arc: str, fault: str, tool: str = "final_result") -> list[ToolCallPart]:
    return play("lead", _SITE, _token(arc, fault), scene=_refusing(tool))


def _prose(call: ToolCallPart) -> str:
    return str(call.args_as_dict()["prose"])


def test_the_registry_names_every_fault_a_spec_injects() -> None:
    assert sorted(FAULTS) == [
        "all-unclear",
        "off-vocabulary",
        "open-value-in-prose",
        "organism-split",
        "repeat-control-test",
        "short-card-reply",
        "sweep-without-controls",
        "syntenic-left-off",
        "unlisted-search",
        "unshown-count",
    ]


def test_an_unlisted_search_is_read_once_then_the_listed_one() -> None:
    calls = _frame("single", "unlisted-search")
    sheet_reads = [a["search_name"] for a in args_of(calls, "set_criterion")]

    assert sheet_reads[:2] == [
        fault_calls.UNLISTED_SEARCH,
        "GenesWithSignalPeptide",
    ]
    assert len(_faulted(calls)) == 1
    assert names(calls)[-2:] == ["set_structure", "final_result"]


def test_an_organism_no_vocabulary_lists_is_sent_once_then_the_sheets() -> None:
    calls = _frame("single", "off-vocabulary")
    organisms = [
        a["params"]["organism"]
        for a in args_of(calls, "set_criterion")
        if "params" in a
    ]

    assert organisms == [[fault_calls.UNLISTED_ORGANISM], [_ORGANISM]]
    assert len(_faulted(calls)) == 1


def test_a_syntenic_binding_leaves_synteny_off_once_then_sets_it() -> None:
    calls = _frame("syntenic-orthologs", "syntenic-left-off")
    synteny = [
        a["params"]["isSyntenic"]
        for a in args_of(calls, "set_criterion")
        if a["search_name"] == "GenesByOrthologs" and "params" in a
    ]

    assert synteny == [None, "yes"]
    assert len(_faulted(calls)) == 1


def test_a_repeated_control_test_sends_the_same_set_once_more() -> None:
    calls = play(
        "verification",
        _SITE,
        _token("controls-test", "repeat-control-test"),
        work_order=verify_order(200),
    )
    tested = args_of(calls, "run_control_tests_on_step")

    assert (
        tested
        == [{"wdk_step_id": STRATEGY_ROOT_WDK_ID, "control_set_id": CONTROL_SET_ID}] * 2
    )
    assert len(_faulted(calls)) == 1
    assert names(calls)[-1] == "final_result"


def test_every_sampled_gene_is_judged_unclear() -> None:
    calls = play(
        "verification",
        _SITE,
        _token("single", "all-unclear"),
        work_order=verify_order(200),
    )
    genes = calls[-1].args_as_dict()["digest"]["review"]["sampledGenes"]

    assert [gene["fits"] for gene in genes] == ["unclear", "unclear"]
    assert made_by_a_fault(calls[-1]) is True


def test_an_unshown_count_is_sent_once_then_the_arcs_reply() -> None:
    calls = _lead("single", "unshown-count")
    finals = [_prose(c) for c in calls if c.tool_name == "final_result"]

    assert finals[0].endswith(f"The strategy returns {LIVE_ROOT_COUNT + 1:,} genes.")
    assert str(LIVE_ROOT_COUNT + 1) not in finals[1]
    assert len(_faulted(calls)) == 1


def test_a_sweep_names_no_control_set_once_then_the_attached_set() -> None:
    calls = _lead("sweep", "sweep-without-controls", "optimize_search_parameters")
    sweeps = args_of(calls, "optimize_search_parameters")

    assert ["control_set_id" in s for s in sweeps] == [False, True]
    assert sweeps[1]["control_set_id"] == CONTROL_SET_ID
    assert len(_faulted(calls)) == 1


def test_a_card_with_a_short_reply_is_sent_once_then_the_arcs() -> None:
    scene = Scene(
        faulted={"consult_user": _REFUSED},
        answers={"frame_problem": asking_frame(_SITE)},
    )
    calls = play("lead", _SITE, _token("consult", "short-card-reply"), scene=scene)
    replies = [str(a["reply"]) for a in args_of(calls, "consult_user")]

    assert replies[0] == fault_calls.SHORT_REPLY
    assert len(replies[1]) >= 20
    assert len(_faulted(calls)) == 1


def test_the_arc_does_not_read_the_refusal_of_a_faults_call_as_its_own() -> None:
    calls = _frame("portal-only", "unlisted-search")
    searched = [
        (made_by_a_fault(call), call.args_as_dict()["search_name"])
        for call in calls
        if call.tool_name == "set_criterion"
    ]

    assert searched[:2] == [
        (True, fault_calls.UNLISTED_SEARCH),
        (False, "GenesByOrthologs"),
    ]
