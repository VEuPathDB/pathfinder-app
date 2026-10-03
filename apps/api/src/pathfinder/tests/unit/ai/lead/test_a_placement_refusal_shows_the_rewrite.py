"""The correction for a number word beside a reference, a noun after a count
reference and a product digit shows the rewrite; the placement rules are stated
once and read by the schema and the Lead's instruction."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.card_reply import PLACEMENT_RULES, REPLY_REFERENCES
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import ProseFault


def _sentence(fault: ProseFault) -> str:
    return unrendered_prose_message([fault]).splitlines()[-1]


def test_a_number_word_fault_shows_the_clause_and_the_rewrite() -> None:
    fault = ProseFault(
        token="at least one predicted transmembrane domain [value:step_5c.min_tm]",
        kind="number_word",
        references=("[value:step_5c.min_tm]",),
    )

    assert _sentence(fault) == (
        "- ``at least one predicted transmembrane domain [value:step_5c.min_tm]``: "
        "``[value:step_5c.min_tm]`` stands in place of the number, so the clause "
        "writes no number word: write 'at least [value:step_x.min_tm] "
        "transmembrane domains', not 'at least one transmembrane domain "
        "[value:step_x.min_tm]'."
    )


def test_a_noun_after_a_count_reference_fault_says_the_reference_carries_it() -> None:
    fault = ProseFault(
        token="[count:step_a] genes",
        kind="noun_after_count",
        references=("[count:step_a]",),
    )

    assert _sentence(fault) == (
        "- ``[count:step_a] genes``: ``[count:step_a]`` renders the count with "
        "its noun, so write no noun after it: 'returns [count:step_a], the "
        "overall result', not 'returns [count:step_a] genes'."
    )


def test_a_product_digit_fault_names_the_record_reference() -> None:
    fault = ProseFault(
        token="2",
        kind="product_text",
        references=("[record:VICG_00034]",),
        record_id="VICG_00034",
    )

    assert _sentence(fault) == (
        "- ``2``: the product of VICG_00034 renders from ``[record:VICG_00034]``; "
        "write the reference alone."
    )


def test_a_digit_no_fact_holds_keeps_its_sentence() -> None:
    assert _sentence(ProseFault(token="3", kind="number")) == (
        "- ``3``: no fact holds it, so take it out."
    )


def test_the_schema_and_the_instruction_state_the_placement_rules() -> None:
    assert REPLY_REFERENCES[-len(PLACEMENT_RULES) :] == PLACEMENT_RULES
    assert " ".join(LEAD_INSTRUCTIONS.split()).count(PLACEMENT_RULES) == 1
