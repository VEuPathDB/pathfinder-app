from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.turn_facts import TurnFacts

_FACT = StatisticFact(
    id="stat_6694be4b",
    kind="gene_check",
    title="Intron support of Afu2g18040",
    rows=[
        StatisticRowFact(name="introns.0.reads", value="0"),
        StatisticRowFact(name="introns.1.reads", value="1,349"),
        StatisticRowFact(name="unread.0.replacement.0.reads", value="1,226"),
        StatisticRowFact(name="frameKept", value="yes", form="boolean"),
    ],
)
_FACTS = TurnFacts(audit_statistics=[_FACT])
_RECORDED = (
    "The annotated intron had no RNA-seq junction support "
    "[stat:stat_6694be4b.introns.0.reads], while an alternative junction with "
    "shifted boundaries had strong support "
    "[stat:stat_6694be4b.unread.0.replacement.0.reads]. The other annotated "
    "intron was supported [stat:stat_6694be4b.introns.1.reads].\n\nThe audit "
    "produced a corrected three-exon coding model that preserves the reading "
    "frame [stat:stat_6694be4b.frameKept]."
)


def test_a_yes_or_no_placed_in_the_recorded_reply_is_refused_with_its_cite() -> None:
    faults = prose_faults(_RECORDED, _FACTS)

    assert faults == [
        ProseFault(
            token="[stat:stat_6694be4b.frameKept]",
            kind="boolean_in_place",
            references=("[cite:stat_6694be4b.frameKept]",),
        )
    ]
    assert unrendered_prose_message(faults).splitlines()[-1] == (
        "- ``[stat:stat_6694be4b.frameKept]`` names a yes or no, which never "
        "stands in the reply: say it in your words and write "
        "``[cite:stat_6694be4b.frameKept]`` after them."
    )


def test_a_yes_or_no_said_in_words_and_cited_is_held() -> None:
    prose = (
        "The corrected model keeps the reading frame [cite:stat_6694be4b.frameKept]."
    )

    assert prose_faults(prose, _FACTS) == []


def test_a_group_reference_offers_no_stat_of_a_yes_or_no() -> None:
    group = "[stat:stat_6694be4b]"

    (fault,) = prose_faults(f"The model holds {group}.", _FACTS)

    assert fault.references == (
        "[stat:stat_6694be4b.introns.0.reads]",
        "[stat:stat_6694be4b.introns.1.reads]",
        "[stat:stat_6694be4b.unread.0.replacement.0.reads]",
    )
