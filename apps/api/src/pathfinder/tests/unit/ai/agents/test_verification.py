"""VERIFY states where a number in its prose is allowed to come from."""

from __future__ import annotations

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS


def _normalized(text: str) -> str:
    """The instructions wrap, so a phrase is asserted without its line breaks."""
    return " ".join(text.split())


def test_a_numeric_parameter_is_restated_only_from_the_tool_that_read_it() -> None:
    assert (
        "A numeric parameter is restated ONLY from the tool result that read it: "
        "``check_study_step``'s ``checks``, a column fit, or the parameters "
        "``get_strategy`` returns. Write the bound value and the realized reading "
        "that result carries; never add an interpretation of your own next to a "
        'number ("80 (top 10%)"). A value that was substituted is a deviation: '
        "report the realized reading and the step that holds it in the note, "
        "and mark its row ``unmet`` with ``answered_by`` empty."
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_a_row_a_step_states_is_met_whatever_the_records_show() -> None:
    assert (
        "``status``: ``met`` when a step states it, whatever the sampled records "
        "show; ``unmet`` when the strategy could state it and no step does, with "
        "``answered_by`` empty;"
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_the_study_step_verdict_is_the_tools() -> None:
    assert (
        "the runtime records those checks as the digest's report, and one not "
        "honored fails the check whatever the digest says"
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_verification_instructions_are_ascii() -> None:
    assert _VERIFICATION_INSTRUCTIONS.isascii()


def test_a_subset_step_states_its_cut_as_the_filters_it_carries() -> None:
    instructions = _normalized(_VERIFICATION_INSTRUCTIONS)

    assert (
        "a subset step with ``subset_filters``, one sentence per filter"
    ) in instructions
    assert "Those filters ARE the subset's cut" in instructions
    assert "never call the cut missing" in instructions


def test_a_study_step_is_never_answered_with_a_rebuild() -> None:
    assert (
        "not something to call unverified or to ask for a rebuild over"
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_a_compute_steps_significance_threshold_is_its_significance_filter() -> None:
    instructions = _normalized(_VERIFICATION_INSTRUCTIONS)

    assert (
        "A compute step's ``significance_threshold`` IS its significance filter"
    ) in instructions
    assert "``get_strategy`` states each study step by what it selects" in instructions


def test_a_study_step_the_site_could_not_read_is_a_pending_check() -> None:
    assert (
        "A step under ``unread_analyses`` is a study step whose analysis the site "
        "did not describe: set ``success`` from the other checks; the runtime lists "
        "that step as pending, never as passed or missing."
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_a_control_test_runs_only_on_a_set_attached_to_the_conversation() -> None:
    instructions = _normalized(_VERIFICATION_INSTRUCTIONS)

    assert (
        "A control test runs only on a control set attached to this conversation, "
        "named by the id ``list_control_sets`` gives it. A gene you sampled or "
        "read is never a control. With no attached set, run no control test and "
        "state that no controls were available."
    ) in instructions
    assert "when available" not in instructions


def test_a_text_requirement_is_shown_by_the_records() -> None:
    assert (
        "a requirement a text value answers is shown only when a record you judged "
        "``yes`` or a column fit names it here. The row stays ``met``"
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_an_unmet_row_names_no_step() -> None:
    assert (
        "An ``unmet`` row that names a step is refused: a combine row whose steps "
        "the strategy joins another way is ``unmet`` with ``answered_by`` empty"
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_a_question_the_researcher_asks_is_no_row() -> None:
    assert (
        'A question the researcher asks ("what was it before?") is answered in '
        "the reply and is never a row"
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)
