"""The deterministic mock's Lead routing: the FRAME->BUILD->VERIFY build journey
plus the consult / variant / attachment branches. These drive the e2e chat
flows, so a regression here silently reds the whole browser suite."""

from __future__ import annotations

import re

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pathfinder.ai.lead.dispatch_messages import build_would_replace_the_strategy
from pathfinder.ai.models.mock import arcs


def _user(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _names(seq: list[ToolCallPart]) -> list[str]:
    return [c.tool_name for c in seq]


def test_build_journey_frames_builds_verifies() -> None:
    msgs: list[ModelMessage] = [_user("...3d7...interpro...")]
    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "verify_strategy",
        "final_result",
    ]


def test_consult_marker_pauses_on_consult_user() -> None:
    msgs: list[ModelMessage] = [_user("Consult me before planning this strategy.")]
    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "consult_user",
    ]


def test_consult_resume_runs_the_build_journey() -> None:
    msgs: list[ModelMessage] = [
        _user("Consult me before planning this strategy."),
        ModelResponse(
            parts=[ToolCallPart(tool_name="consult_user", args={}, tool_call_id="c1")]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="consult_user", content="answered", tool_call_id="c1"
                ),
                UserPromptPart(content="The user answered your questions: ..."),
            ]
        ),
    ]
    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "verify_strategy",
        "final_result",
    ]


def test_variant_marker_compares_variants() -> None:
    msgs: list[ModelMessage] = [_user("Compare two search variants for kinases.")]
    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "compare_search_variants",
        "final_result",
    ]


def test_an_attachment_classifies_before_it_seeds_a_control_set() -> None:
    """Every arc classifies first: the gate hides the rest until it does."""
    msgs: list[ModelMessage] = [
        _user("Use these genes as my positive controls."),
        _user("Attached gene-ID list from controls.csv: PF3D7_0709000, PF3D7_1133400"),
    ]

    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "build_control_set",
        "final_result",
    ]


def test_a_seeded_control_set_is_named_after_the_file_it_came_from() -> None:
    """Two uploads must not produce two rows a reader cannot tell apart."""
    msgs: list[ModelMessage] = [
        _user("Use these genes as my positive controls."),
        _user("Attached gene-ID list from msp-set.csv: PF3D7_0102200, PF3D7_0207600"),
    ]

    call = next(
        c for c in arcs._lead_sequence(msgs) if c.tool_name == "build_control_set"
    )

    assert call.args == {
        "name": "Controls from msp-set.csv",
        "positive_ids": ["PF3D7_0102200", "PF3D7_0207600"],
    }


def test_a_save_request_creates_a_workbench_gene_set() -> None:
    """The save the user asks for is the workbench tool, never a memory note."""
    msgs: list[ModelMessage] = [
        _user("Save the 155 genes as a gene set called gametocyte candidates.")
    ]

    names = _names(arcs._lead_sequence(msgs))

    assert names == [
        "classify_user_intent",
        "create_workbench_gene_set",
        "final_result",
    ]
    assert "remember" not in names


def test_plain_prompt_echoes_only() -> None:
    msgs: list[ModelMessage] = [_user("hello there")]
    assert _names(arcs._lead_sequence(msgs)) == ["final_result"]


def _prose(seq: list[ToolCallPart]) -> str:
    return str(seq[-1].args_as_dict()["prose"])


# ── The verification-feedback arc ───────────────────────────────────

_BROADEN = "Add InterPro PF00069 (Pkinase) and EC 2.7.-.- to broaden kinases."
_FIX = "Fix the phylogenetic pattern by loosening to %MAMM:N%pfal:Y%."


def test_a_broadening_request_builds_and_reports_the_zero_result() -> None:
    seq = arcs._lead_sequence([_user(_BROADEN)])

    assert _names(seq) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "verify_strategy",
        "final_result",
    ]
    assert "returned 0" in _prose(seq)
    assert seq[-1].args_as_dict()["nextState"] == "await_user"


def test_the_fix_request_then_verifies_cleanly() -> None:
    seq = arcs._lead_sequence([_user(_FIX)])

    assert "Verified end-to-end" in _prose(seq)
    assert seq[-1].args_as_dict()["nextState"] == "complete"


def test_the_feedback_prose_states_the_failure_and_not_the_success() -> None:
    # The specs read these two apart by their text, so they must not overlap.
    feedback = _prose(arcs._lead_sequence([_user(_BROADEN)]))
    success = _prose(arcs._lead_sequence([_user(_FIX)]))

    assert not re.search(r"verified end-to-end|root size", feedback, re.IGNORECASE)
    assert not re.search(r"returned 0|too narrow|loosen", success, re.IGNORECASE)


def test_the_digest_agrees_with_the_lead_about_failure() -> None:
    # A digest that reports success over a failed build is the contradiction
    # the ledger cannot show the user.
    assert arcs.verification_succeeds(_FIX) is True
    assert arcs.verification_succeeds(_BROADEN) is False


# ── Site-aware canned specs ─────────────────────────────────────────


def test_the_canned_spec_takes_the_organism_of_the_site_it_runs_on() -> None:
    spec = arcs.spec_for("create step", "cryptodb")

    assert spec.criteria[0].values["organism"] == ["Cryptosporidium parvum Iowa II"]


def test_a_broadening_request_frames_two_leaves() -> None:
    spec = arcs.spec_for(_BROADEN, "plasmodb")

    assert [c.search_name for c in spec.criteria] == ["GenesByText", "GenesByTaxon"]


def test_a_go_request_frames_the_go_search() -> None:
    spec = arcs.spec_for("build a GO term strategy for kinases", "plasmodb")

    assert [c.search_name for c in spec.criteria] == ["GenesByGoTerm"]


def test_an_all_parameter_request_frames_three_search_types() -> None:
    spec = arcs.spec_for("Build a comprehensive kinase strategy", "plasmodb")

    assert [c.search_name for c in spec.criteria] == [
        "GenesByText",
        "GenesByGoTerm",
        "GenesByTaxon",
    ]


def test_an_impact_question_does_not_rebuild() -> None:
    # It names InterPro, which otherwise routes to a build.
    seq = arcs._lead_sequence(
        [_user("What's the impact of switching the InterPro/GO combine to INTERSECT?")]
    )

    assert _names(seq) == ["final_result"]


def test_an_edit_marker_routes_to_the_edit_dispatch() -> None:
    """An edit is a build, so the arc verifies what it changed."""
    msgs: list[ModelMessage] = [
        _user("Swap the organism on the taxon criterion and keep the rest.")
    ]
    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "edit_strategy",
        "verify_strategy",
        "final_result",
    ]


def test_a_remember_request_stores_the_preference_and_builds_nothing() -> None:
    msgs: list[ModelMessage] = [
        _user("Please remember for future sessions: I work with P. falciparum 3D7.")
    ]

    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "remember",
        "final_result",
    ]


def test_a_context_statement_answers_in_prose_and_builds_nothing() -> None:
    msgs: list[ModelMessage] = [
        _user("I'm investigating virulence factors in Leishmania major")
    ]

    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "final_result",
    ]


def test_the_classification_is_made_once_per_turn() -> None:
    """A second turn re-classifies; the run's first classification is not reused."""
    first_turn: list[ModelMessage] = [
        _user("...3d7...interpro..."),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="classify_user_intent", args={}, tool_call_id="c0"
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="classify_user_intent",
                    content="ok",
                    tool_call_id="c0",
                )
            ]
        ),
    ]
    second_turn: list[ModelMessage] = [
        *first_turn,
        _user("Swap the organism on the taxon criterion and keep the rest."),
    ]

    assert arcs.lead_script(second_turn).tool_name == "classify_user_intent"


# ── The recall arc ──────────────────────────────────────────────────

_RECALL = "Recap what I have asked so far."


def test_the_recall_arc_reads_the_frame_section_first() -> None:
    seq = arcs._lead_sequence([_user(_RECALL)])

    assert _names(seq) == ["read_ledger_section", "final_result"]
    assert seq[0].args_as_dict()["section"] == "frame"


def test_the_recall_arc_answers_with_the_section_it_read() -> None:
    msgs: list[ModelMessage] = [
        _user(_RECALL),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="read_ledger_section",
                    args={"section": "frame"},
                    tool_call_id="r1",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="read_ledger_section",
                    content="## Frame (full)\n- goal: kinases",
                    tool_call_id="r1",
                )
            ]
        ),
    ]

    seq = arcs._lead_sequence(msgs)

    assert _prose(seq) == (
        "This thread already carries: ## Frame (full)\n- goal: kinases"
    )


def test_the_recall_arc_dispatches_no_sub_agent() -> None:
    seq = arcs._lead_sequence([_user(_RECALL)])

    assert "frame_problem" not in _names(seq)
    assert "build_strategy" not in _names(seq)
    assert "verify_strategy" not in _names(seq)


# ── The refused-build arc ───────────────────────────────────────────

_SECOND_BUILD = "Build a comprehensive kinase strategy"


def _refused_build_turn(prompt: str = _SECOND_BUILD) -> list[ModelMessage]:
    """A turn that classified, framed, called build_strategy and was refused."""
    return [
        _user(prompt),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="classify_user_intent", args={}, tool_call_id="c1"
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="classify_user_intent", content="ok", tool_call_id="c1"
                )
            ]
        ),
        ModelResponse(
            parts=[ToolCallPart(tool_name="frame_problem", args={}, tool_call_id="f1")]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="frame_problem",
                    content="Structure set: 3 criteria",
                    tool_call_id="f1",
                )
            ]
        ),
        ModelResponse(
            parts=[ToolCallPart(tool_name="build_strategy", args={}, tool_call_id="b1")]
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content=build_would_replace_the_strategy(1),
                    tool_name="build_strategy",
                    tool_call_id="b1",
                )
            ]
        ),
    ]


def _absent_build_turn(prompt: str = "...3d7...interpro...") -> list[ModelMessage]:
    """The same turn, with ``build_strategy`` withheld instead of refused."""
    turn = _refused_build_turn(prompt)
    turn[-1] = ModelRequest(
        parts=[
            RetryPromptPart(
                content="Unknown tool name: 'build_strategy'. Available tools: 'x'",
                tool_name="build_strategy",
                tool_call_id="b1",
            )
        ]
    )
    return turn


def test_a_withheld_build_stops_before_verification() -> None:
    """The gate hides the tool, so the arc meets the refusal as an absence."""
    seq = arcs._lead_sequence(_absent_build_turn())

    assert _names(seq) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "final_result",
    ]


def test_the_mock_reads_the_real_refusal_message() -> None:
    assert arcs._BUILD_REFUSED_MARKER in build_would_replace_the_strategy(1)


def test_a_refused_build_stops_before_verification() -> None:
    seq = arcs._lead_sequence(_refused_build_turn())

    assert _names(seq) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "final_result",
    ]
    assert "verify_strategy" not in _names(seq)


def test_the_refused_build_answers_with_the_edit_tool_and_no_success() -> None:
    prose = _prose(arcs._lead_sequence(_refused_build_turn()))

    assert "edit_strategy" in prose
    assert not re.search(
        r"verified end-to-end|verification passed|root size|candidate drug targets",
        prose,
        re.IGNORECASE,
    )
    assert not re.search(r"returned 0|too narrow|loosen", prose, re.IGNORECASE)


def test_the_refused_build_leaves_the_turn_with_the_user() -> None:
    seq = arcs._lead_sequence(_refused_build_turn())

    assert seq[-1].args_as_dict()["nextState"] == "await_user"


def test_the_script_answers_the_refusal_instead_of_verifying() -> None:
    assert arcs.lead_script(_refused_build_turn()).tool_name == "final_result"


def test_a_refused_consult_resume_reports_the_refusal_too() -> None:
    msgs: list[ModelMessage] = [
        _user("Consult me before planning this strategy."),
        ModelResponse(
            parts=[ToolCallPart(tool_name="consult_user", args={}, tool_call_id="c0")]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="consult_user", content="answered", tool_call_id="c0"
                )
            ]
        ),
        ModelResponse(
            parts=[ToolCallPart(tool_name="build_strategy", args={}, tool_call_id="b1")]
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content=build_would_replace_the_strategy(2),
                    tool_name="build_strategy",
                    tool_call_id="b1",
                )
            ]
        ),
    ]

    assert "edit_strategy" in _prose(arcs._lead_sequence(msgs))


def test_an_earlier_turns_refusal_does_not_bend_the_next_turn() -> None:
    msgs: list[ModelMessage] = [
        *_refused_build_turn(),
        ModelResponse(
            parts=[ToolCallPart(tool_name="final_result", args={}, tool_call_id="r1")]
        ),
        _user("create step for tryptophan synthase"),
    ]

    assert _names(arcs._lead_sequence(msgs)) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "verify_strategy",
        "final_result",
    ]


def test_a_retry_from_another_tool_does_not_stop_the_build_arc() -> None:
    msgs: list[ModelMessage] = [
        _user(_SECOND_BUILD),
        ModelResponse(
            parts=[ToolCallPart(tool_name="frame_problem", args={}, tool_call_id="f1")]
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content="FRAME bound nothing.",
                    tool_name="frame_problem",
                    tool_call_id="f1",
                )
            ]
        ),
    ]

    assert "verify_strategy" in _names(arcs._lead_sequence(msgs))
