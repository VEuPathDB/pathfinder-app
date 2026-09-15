"""What the Lead's standing instructions must say."""

from __future__ import annotations

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_instructions_name_every_eda_tool_in_call_order() -> None:
    order = [
        "search_eda_studies",
        "describe_eda_study",
        "open_eda_analysis",
        "set_eda_filters",
        "preview_eda_subset",
        "run_eda_compute",
        "create_eda_step",
    ]
    positions = [LEAD_INSTRUCTIONS.index(name) for name in order]
    assert positions == sorted(positions)


def test_the_instructions_ask_for_a_stated_premise_to_be_checked() -> None:
    assert "A premise the question states as fact is checked" in LEAD_INSTRUCTIONS
    assert "answering around a false premise" in LEAD_INSTRUCTIONS


def test_the_instructions_say_when_eda_beats_a_classic_search() -> None:
    assert "sample-level" in LEAD_INSTRUCTIONS
    assert "eda_analysis_spec" in LEAD_INSTRUCTIONS


def test_the_instructions_forbid_quoting_a_count_before_a_preview() -> None:
    assert "preview_eda_subset" in LEAD_INSTRUCTIONS
    assert "before you state a count" in LEAD_INSTRUCTIONS


def test_the_instructions_say_the_compute_runs_before_the_step() -> None:
    index_compute = LEAD_INSTRUCTIONS.index("run_eda_compute")
    index_step = LEAD_INSTRUCTIONS.index("create_eda_step")
    assert index_compute < index_step
    assert "completes" in LEAD_INSTRUCTIONS


def test_the_eda_section_asks_for_a_caption_on_every_plot() -> None:
    """The figure prints the model's sentence, so the loop must ask for one."""
    eda_section = LEAD_INSTRUCTIONS[
        LEAD_INSTRUCTIONS.index("## EDA: sample-level data") : LEAD_INSTRUCTIONS.index(
            "## User-facing voice"
        )
    ]
    assert "caption" in eda_section


def test_the_eda_loop_ends_with_verification() -> None:
    """An exported study step is a built step, so the loop closes with VERIFY."""
    eda_section = LEAD_INSTRUCTIONS[
        LEAD_INSTRUCTIONS.index("## EDA: sample-level data") :
    ]
    index_step = eda_section.index("create_eda_step")
    assert "verify_strategy" in eda_section[index_step:]


def test_the_instructions_are_ascii_only() -> None:
    assert LEAD_INSTRUCTIONS.isascii()


def test_the_lead_writes_a_preservation_claim_from_the_ledger_diff() -> None:
    assert "ledger.frame.diff" in LEAD_INSTRUCTIONS
    assert "preserved" in LEAD_INSTRUCTIONS


def test_frame_states_a_disposition_for_every_criterion_already_there() -> None:
    normalized = _flat(_FRAME_INSTRUCTIONS)
    assert "changes" in normalized
    assert "kept" in normalized
    assert "dropped" in normalized


def test_frame_is_told_not_to_re_bind_an_untouched_criterion() -> None:
    normalized = _flat(_FRAME_INSTRUCTIONS)
    assert "does not mention is kept" in normalized
    assert "must not be re-bound" in normalized


def test_the_instructions_answer_a_missing_building_tool_with_a_reclassify() -> None:
    instructions = _flat(LEAD_INSTRUCTIONS)

    assert "A missing building tool is a misclassification" in instructions
    assert "your FIRST action is ``classify_user_intent`` again" in instructions


def test_the_instructions_forbid_telling_the_user_a_tool_is_unavailable() -> None:
    instructions = _flat(LEAD_INSTRUCTIONS)

    assert "NEVER tell the user that a tool is unavailable this turn" in instructions
    assert "never ask them to retry the request" in instructions


def test_the_lead_instructions_name_the_tool_that_starts_over() -> None:
    assert "``clear_strategy``" in _flat(LEAD_INSTRUCTIONS)


def test_the_lead_is_told_to_route_an_edit_to_the_edit_tool() -> None:
    """The prose names the route; the gate hides ``frame_problem`` for it."""
    assert "the pinned Operational Spec has criteria, call ``edit_strategy``" in _flat(
        LEAD_INSTRUCTIONS
    )


def _eda_section() -> str:
    return LEAD_INSTRUCTIONS[
        LEAD_INSTRUCTIONS.index("## EDA: sample-level data") : LEAD_INSTRUCTIONS.index(
            "## User-facing voice"
        )
    ]


def test_the_export_can_take_the_place_of_a_step_already_held() -> None:
    assert "replace_step_id" in _flat(_eda_section())


def test_an_eda_backed_criterion_never_reaches_the_framing_tools() -> None:
    section = _flat(_eda_section())

    assert "do NOT route it through frame_problem or build_strategy" in section


def test_the_user_is_never_asked_for_an_analysis_specification() -> None:
    section = _flat(_eda_section())

    assert "Never ask the user for an analysis specification" in section
    assert "create_eda_step writes it" in section


def test_the_lead_removes_a_step_with_the_delete_tool() -> None:
    instructions = _flat(LEAD_INSTRUCTIONS)

    assert "A step the user wants gone is removed with ``delete_step``" in instructions
    assert "Never dispatch a framing or building pass to remove a step" in instructions


def test_the_instructions_name_the_four_fields_the_contract_reads() -> None:
    instructions = _flat(LEAD_INSTRUCTIONS)

    assert "``strategy_changed`` against every write the turn made" in instructions
    assert "``asked_questions``" in instructions
    assert "``analysed_gene_set_ids``" in instructions
    assert "``sources``" in instructions
    assert "a single correction listing every mismatch" in instructions


def test_a_fact_about_a_gene_is_read_from_its_record() -> None:
    instructions = _flat(LEAD_INSTRUCTIONS)

    assert "A fact about a gene is read from its record" in instructions
    assert "``read_gene_record``" in instructions


def test_the_two_research_reads_answer_what_the_record_does_not() -> None:
    instructions = _flat(LEAD_INSTRUCTIONS)

    assert "the biology the record does not hold" in instructions
    assert (
        "a name, a claim or a current event neither the catalog nor the record"
        in instructions
    )
