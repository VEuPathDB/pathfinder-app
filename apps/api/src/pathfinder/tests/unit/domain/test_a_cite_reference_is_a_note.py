"""A ``stat`` reference renders its value in place, a ``cite`` reference a note after the words before it, and each kind is refused on a value of the other."""

from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import (
    ProseFault,
    nested_text,
    prose_faults,
    render_reply,
    shown_reply,
)
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
            name="review.cause", value="The junction has no reads.", form="sentence"
        ),
        StatisticRowFact(name="finding.reads", value="1226"),
    ],
)
_FACTS = TurnFacts(audit_statistics=[_FACT])


def test_a_stat_reference_renders_the_value_where_it_stands() -> None:
    prose = (
        "It is a [stat:stat_0a1b2c3d.finding.certainty] certainty error over "
        "[stat:stat_0a1b2c3d.finding.reads] reads."
    )

    assert (
        render_reply(prose, _FACTS) == "It is a high certainty error over 1226 reads."
    )


def test_a_cite_reference_is_a_note_after_the_words_before_it() -> None:
    prose = (
        "Confidence is high [cite:stat_0a1b2c3d.finding.certainty], and the "
        "frame is kept [cite:stat_0a1b2c3d.finding.frameKept]."
    )

    assert shown_reply(prose, _FACTS, "a-") == (
        "Confidence is high[^a-1], and the frame is kept[^a-2].\n\n"
        "[^a-1]: finding certainty: high\n[^a-2]: finding frame kept: yes"
    )


def test_a_sentence_cited_twice_is_quoted_once() -> None:
    prose = (
        "The review found no support [cite:stat_0a1b2c3d.review.cause] and kept "
        "the error [cite:stat_0a1b2c3d.review.cause]."
    )

    assert shown_reply(prose, _FACTS, "b-") == (
        "The review found no support[^b-1] and kept the error[^b-1].\n\n"
        "[^b-1]: review cause: The junction has no reads."
    )


def test_the_rendered_reply_the_rules_read_holds_no_notes() -> None:
    prose = "Should the review run again on the high [cite:stat_0a1b2c3d.finding.certainty]?"

    assert render_reply(prose, _FACTS) == "Should the review run again on the high[^1]?"


def test_two_labels_give_two_replies_notes_of_their_own() -> None:
    prose = "Kept [cite:stat_0a1b2c3d.finding.frameKept]."

    assert (shown_reply(prose, _FACTS, "m1-"), shown_reply(prose, _FACTS, "m2-")) == (
        "Kept[^m1-1].\n\n[^m1-1]: finding frame kept: yes",
        "Kept[^m2-1].\n\n[^m2-1]: finding frame kept: yes",
    )


def test_a_sentence_written_in_place_is_refused_with_its_cite() -> None:
    prose = "The review says [stat:stat_0a1b2c3d.review.cause]"

    faults = prose_faults(prose, _FACTS)

    assert faults == [
        ProseFault(
            token="[stat:stat_0a1b2c3d.review.cause]",
            kind="sentence_in_place",
            references=("[cite:stat_0a1b2c3d.review.cause]",),
        )
    ]
    assert unrendered_prose_message(faults).splitlines()[-1] == (
        "- ``[stat:stat_0a1b2c3d.review.cause]`` names a stored sentence, which "
        "never stands in the reply: say it in your words and write "
        "``[cite:stat_0a1b2c3d.review.cause]`` after them."
    )


def test_a_cited_number_is_refused_with_its_stat() -> None:
    prose = "The junction is well read [cite:stat_0a1b2c3d.finding.reads]."

    faults = prose_faults(prose, _FACTS)

    assert faults == [
        ProseFault(
            token="[cite:stat_0a1b2c3d.finding.reads]",
            kind="cited_number",
            references=("[stat:stat_0a1b2c3d.finding.reads]",),
        )
    ]
    assert unrendered_prose_message(faults).splitlines()[-1] == (
        "- ``[cite:stat_0a1b2c3d.finding.reads]`` names a number, which the reply "
        "writes in place: write ``[stat:stat_0a1b2c3d.finding.reads]``."
    )


def test_a_word_may_be_written_in_place_or_cited() -> None:
    prose = (
        "A [stat:stat_0a1b2c3d.finding.certainty] certainty error, high "
        "[cite:stat_0a1b2c3d.finding.certainty]."
    )

    assert prose_faults(prose, _FACTS) == []


def test_nested_text_places_values_and_cites_in_parentheses() -> None:
    prose = (
        "The run kept [stat:stat_0a1b2c3d.finding.reads] reads, and the review "
        "found no support [cite:stat_0a1b2c3d.review.cause]."
    )

    assert nested_text(prose, _FACTS) == (
        "The run kept 1226 reads, and the review found no support "
        "(The junction has no reads.)."
    )


_GENOME = StatisticFact(
    id="stat_9e8d7c6b",
    kind="audit_finding",
    title="Finding 2 of audit run 0b6f3a52-6a1e-4c55-9a62-1f1d2a3b4c5d",
    rows=[
        StatisticRowFact(
            name="finding.genome", value="Plasmodium yoelii yoelii 17X", form="word"
        )
    ],
)


def test_a_held_name_placed_by_its_reference_is_never_refused() -> None:
    facts = TurnFacts(audit_statistics=[_GENOME])
    prose = "The finding is in [stat:stat_9e8d7c6b.finding.genome]."

    assert (prose_faults(prose, facts), render_reply(prose, facts)) == (
        [],
        "The finding is in Plasmodium yoelii yoelii 17X.",
    )


def test_a_held_name_written_out_names_the_reference_that_places_it() -> None:
    facts = TurnFacts(audit_statistics=[_GENOME])

    faults = prose_faults("The finding is in Plasmodium yoelii yoelii 17X.", facts)

    assert faults == [
        ProseFault(
            token="17X",
            kind="number",
            references=("[stat:stat_9e8d7c6b.finding.genome]",),
        )
    ]


def test_a_cite_that_names_nothing_held_leaves_no_gap() -> None:
    prose = "The review kept the error [cite:stat_0a1b2c3d.review.missing]."

    assert shown_reply(prose, _FACTS, "c-") == "The review kept the error."
