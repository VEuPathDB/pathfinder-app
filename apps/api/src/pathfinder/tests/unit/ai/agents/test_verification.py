"""VERIFY states where a number in its prose is allowed to come from."""

from __future__ import annotations

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS


def _normalized(text: str) -> str:
    """The instructions wrap, so a phrase is asserted without its line breaks."""
    return " ".join(text.split())


def test_a_numeric_parameter_is_restated_only_from_the_constraint_report() -> None:
    assert (
        "A numeric parameter is restated ONLY from its ``constraint_report`` "
        "entry. Write the bound value and the realized reading that entry "
        "carries; never add an interpretation of your own next to a number "
        '("80 (top 10%)"). An entry whose status is substituted is a '
        "deviation: report the realized reading, set ``honored=False``, and "
        "carry it into ``caveats``."
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
        "did not describe: set ``success`` from the other checks and name that step "
        "in ``caveats`` as a pending check, never as passed or missing."
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_each_step_is_tested_once_with_the_whole_control_set() -> None:
    instructions = _normalized(_VERIFICATION_INSTRUCTIONS)

    assert (
        "Test each step once, with every positive and every negative control id "
        "in one call. Never test a subset of ids already tested on that step"
    ) in instructions
