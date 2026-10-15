"""A step counts in the noun of its own records, so a groups step under a proteins
result reads as groups in its row and in a reference to it."""

from __future__ import annotations

from pathfinder.domain.reference_placement import misplacements
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.turn_facts import StepFact, TurnFacts

_ORTHO = TurnFacts(
    record_noun="sequence",
    steps=[
        StepFact(
            step_id="step_pattern",
            display_name="Phyletic Pattern",
            count=297,
            record_noun="group",
        ),
        StepFact(
            step_id="step_proteins",
            display_name="Transform Groups to Proteins",
            count=103766,
            record_noun="sequence",
        ),
    ],
    root_count=300,
)


def test_each_step_row_counts_its_own_records() -> None:
    assert _ORTHO.lines()[:3] == [
        "Phyletic Pattern: 297 groups",
        "Transform Groups to Proteins: 103,766 sequences",
        "Result: 300 sequences",
    ]


def test_a_step_reference_counts_its_own_records_and_absorbs_their_noun() -> None:
    assert render_reply(
        "The pattern keeps [count:step_pattern] groups, [root] in 3D7.", _ORTHO
    ) == ("The pattern keeps 297 groups, 300 sequences in 3D7.")


def test_a_noun_after_a_step_reference_is_misplaced_in_any_noun_the_facts_count() -> (
    None
):
    found = misplacements(
        "The pattern keeps [count:step_pattern] groups.", _ORTHO.counted_nouns()
    )

    assert [m.token for m in found] == ["[count:step_pattern] groups"]
