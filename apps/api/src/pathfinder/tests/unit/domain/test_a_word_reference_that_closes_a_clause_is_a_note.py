"""A reference to a word or a sentence renders the word inside a clause, and a numbered note when it closes the clause."""

from __future__ import annotations

from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.turn_facts import TurnFacts

_FACT = StatisticFact(
    id="stat_0a1b2c3d",
    kind="audit_finding",
    title="Finding 1 of audit run 0b6f3a52-6a1e-4c55-9a62-1f1d2a3b4c5d",
    rows=[
        StatisticRowFact(name="finding.certainty", value="high", form="word"),
        StatisticRowFact(name="finding.frameKept", value="yes", form="word"),
        StatisticRowFact(
            name="review.cause", value="The junction has no reads.", form="word"
        ),
        StatisticRowFact(name="finding.reads", value="1226"),
    ],
)
_FACTS = TurnFacts(audit_statistics=[_FACT])


def test_a_word_reference_inside_a_clause_renders_the_word() -> None:
    prose = "It is a [stat:stat_0a1b2c3d.finding.certainty] certainty error."

    assert render_reply(prose, _FACTS) == "It is a high certainty error."


def test_a_word_reference_that_closes_a_clause_renders_a_note() -> None:
    prose = (
        "Confidence is high [stat:stat_0a1b2c3d.finding.certainty]; the frame is "
        "kept [stat:stat_0a1b2c3d.finding.frameKept]."
    )

    assert render_reply(prose, _FACTS) == (
        "Confidence is high[^1]; the frame is kept[^2].\n\n"
        "[^1]: certainty: high\n[^2]: frame kept: yes"
    )


def test_a_sentence_cited_twice_is_quoted_once() -> None:
    prose = (
        "The review found no support [stat:stat_0a1b2c3d.review.cause], and the "
        "model stays an error [stat:stat_0a1b2c3d.review.cause]."
    )

    assert render_reply(prose, _FACTS) == (
        "The review found no support[^1], and the model stays an error[^1].\n\n"
        "[^1]: cause: The junction has no reads."
    )


def test_a_number_reference_renders_in_place_wherever_it_stands() -> None:
    prose = "The junction holds [stat:stat_0a1b2c3d.finding.reads]."

    assert render_reply(prose, _FACTS) == "The junction holds 1226."


def test_a_reference_before_another_reference_closes_its_clause() -> None:
    prose = (
        "It is kept [stat:stat_0a1b2c3d.finding.frameKept] "
        "[stat:stat_0a1b2c3d.finding.reads]."
    )

    assert render_reply(prose, _FACTS) == (
        "It is kept[^1] 1226.\n\n[^1]: frame kept: yes"
    )


def test_a_note_reference_is_no_fault() -> None:
    prose = "Confidence is high [stat:stat_0a1b2c3d.finding.certainty]."

    assert prose_faults(prose, _FACTS) == []
