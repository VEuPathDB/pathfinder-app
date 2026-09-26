"""Each fault makes its wrong call in place of the arc's, the arc makes the
right call once the refusal is back, and the wrong call comes once a turn."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)
from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_workspace
from pathfinder.ai.lead.dispatch_messages import stopped_pass_work_order
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.models.mock import fault_calls
from pathfinder.ai.models.mock.edit_arcs import DELETED_PROSE
from pathfinder.ai.models.mock.faults import FAULTS, made_by_a_fault
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.step_rationale import MAX_REASON_CHARS
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
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

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
        "long-reason",
        "misnamed-deletion",
        "misstated-count",
        "off-vocabulary",
        "repeat-control-test",
        "short-card-reply",
        "sweep-without-controls",
        "syntenic-left-off",
        "transcript-count",
        "unbacked-controls",
        "unlisted-search",
        "value-as-term",
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


def test_a_value_passed_as_the_term_is_sent_once_then_the_parameter() -> None:
    calls = _frame("single", "value-as-term")
    terms = [a["why"]["term"] for a in args_of(calls, "set_criterion") if "why" in a]

    assert terms == [_ORGANISM, "organism"]
    assert len(_faulted(calls)) == 1


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


def test_a_long_reason_is_refused_until_the_pass_stops() -> None:
    calls = _frame("intersect", "long-reason")
    reasons = [
        a["why"]["reason"]
        for a in args_of(calls, "set_criterion")
        if a["criterion_id"] == "tm_domains" and "why" in a
    ]

    assert len(fault_calls.LONG_REASON) > MAX_REASON_CHARS
    assert reasons[:4] == [fault_calls.LONG_REASON] * 4
    assert fault_calls.LONG_REASON not in reasons[4:]
    assert len(_faulted(calls)) == 4


def test_the_pass_that_continues_a_stopped_pass_binds_as_the_arc_does() -> None:
    spec = OperationalSpec(
        goal="secreted membrane genes",
        criteria=[
            Criterion(
                id="signal_peptide",
                text="signal peptide genes",
                search_name="GenesWithSignalPeptide",
                role="seed",
            )
        ],
    )
    stop = PhaseStop(role="frame", reason=PhaseStopReason.TOOL_RETRIES)
    order = stopped_pass_work_order(spec, "secreted membrane genes", stop)

    calls = _frame("intersect", "long-reason", work_order=order)

    assert _faulted(calls) == []
    assert names(calls)[-1] == "final_result"


def test_a_repeated_control_test_sends_half_the_positives_once() -> None:
    calls = play(
        "verification",
        _SITE,
        _token("controls-test", "repeat-control-test"),
        work_order=verify_order(200),
    )
    tested = args_of(calls, "run_control_tests_on_step")
    positives = SiteValues.for_site(_SITE).controls.positive_ids

    assert [t["positive_controls"] for t in tested] == [
        positives,
        positives[: max(1, len(positives) // 2)],
    ]
    assert {t["wdk_step_id"] for t in tested} == {STRATEGY_ROOT_WDK_ID}
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


def test_a_gene_count_named_in_transcripts_is_restated_in_genes() -> None:
    calls = _lead("single", "transcript-count")
    finals = [_prose(c) for c in calls if c.tool_name == "final_result"]

    assert [
        f.endswith(f"returns {LIVE_ROOT_COUNT:,} transcripts.") for f in finals
    ] == [
        True,
        False,
    ]
    assert finals[1].endswith(f"returns {LIVE_ROOT_COUNT:,} genes.")
    assert len(_faulted(calls)) == 1


def test_a_count_no_step_holds_is_restated_as_the_root() -> None:
    calls = _lead("single", "misstated-count")
    finals = [_prose(c) for c in calls if c.tool_name == "final_result"]

    assert finals[0].endswith(f"returns {2 * LIVE_ROOT_COUNT + 1:,} genes.")
    assert finals[1].endswith(f"returns {LIVE_ROOT_COUNT:,} genes.")
    assert len(_faulted(calls)) == 1


def test_a_control_count_no_test_holds_is_claimed_once() -> None:
    calls = _lead("controls-test", "unbacked-controls")
    finals = [_prose(c) for c in calls if c.tool_name == "final_result"]
    total = len(SiteValues.for_site(_SITE).controls.positive_ids) + 1

    assert finals[0].endswith(f"It returned {total} of {total} positive controls.")
    assert "positive controls" not in finals[1]
    assert len(_faulted(calls)) == 1


def test_a_sweep_names_no_controls_once_then_the_saved_set() -> None:
    calls = _lead("sweep", "sweep-without-controls", "optimize_search_parameters")
    sweeps = args_of(calls, "optimize_search_parameters")

    assert ["control_set_id" in s for s in sweeps] == [False, True]
    assert sweeps[1]["control_set_id"] == CONTROL_SET_ID
    assert "positive_controls" not in sweeps[0]
    assert len(_faulted(calls)) == 1


def test_a_card_with_a_short_reply_is_sent_once_then_the_arcs() -> None:
    calls = _lead("consult", "short-card-reply", "consult_user")
    replies = [str(a["reply"]) for a in args_of(calls, "consult_user")]

    assert replies[0] == fault_calls.SHORT_REPLY
    assert len(replies[1]) >= 20
    assert len(_faulted(calls)) == 1


def test_a_reply_naming_the_standing_step_is_sent_once_after_the_card() -> None:
    thread = Scene(
        faulted={"final_result": _REFUSED},
        answers={
            "get_live_strategy_state": {
                "steps": [
                    {"stepId": "step_tm", "searchName": "GenesByTransmembraneDomains"}
                ]
            }
        },
    )

    calls = play(
        "lead", _SITE, _token("delete-step-card", "misnamed-deletion"), scene=thread
    )
    finals = [_prose(c) for c in calls if c.tool_name == "final_result"]

    assert names(calls)[:3] == [
        "classify_user_intent",
        "get_live_strategy_state",
        "delete_step",
    ]
    assert finals == [fault_calls.MISNAMED_DELETION, DELETED_PROSE]
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


def test_a_long_reason_reads_the_bound_criterion_from_the_pinned_workspace() -> None:
    state = AgentToolState()
    state.frame_set_criterion(
        Criterion(
            id="signal_peptide",
            text="signal peptide genes",
            search_name="GenesWithSignalPeptide",
            resolved_params={"organism": MultiPickValue(values=[_ORGANISM])},
        )
    )
    workspace = pinned_frame_workspace(agent_run_context(agent_state=state)) or ""
    compacted: list[ModelMessage] = [
        ModelRequest(
            parts=[UserPromptPart(content=_FRAME_ORDER)], instructions=workspace
        )
    ]
    intended = scripted_call(
        "set_criterion",
        {
            "criterion_id": "tm_domains",
            "search_name": "GenesByTransmembraneDomains",
            "params": {"organism": [_ORGANISM]},
            "why": {"basis": "parameter", "term": "organism", "reason": "sets it"},
        },
    )

    wrong = fault_calls.long_reason(compacted)(intended)

    assert wrong is not None
    assert wrong.args_as_dict()["why"]["reason"] == fault_calls.LONG_REASON
