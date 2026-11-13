"""A count comparison is answered by the read-only comparison, never by a combine."""

from __future__ import annotations

from strategist.ai.lead._lead_instructions import LEAD_INSTRUCTIONS


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_instructions_no_longer_build_one_step_per_organism() -> None:
    assert "one such step per organism" not in _flat(LEAD_INSTRUCTIONS)


def test_the_instructions_route_a_count_comparison_to_the_read_only_comparison() -> (
    None
):
    rules = _flat(LEAD_INSTRUCTIONS)

    assert (
        "A comparison of counts is a question, answered by ``compare_search_variants``"
        in rules
    )


def test_the_instructions_say_what_the_lead_does_with_each_comparison() -> None:
    rules = _flat(LEAD_INSTRUCTIONS)

    assert "a variant whose scoring failed is reported as failed" in rules
    assert (
        "over a strategy that holds a step, the answers go to ``edit_strategy``"
        in rules
    )
