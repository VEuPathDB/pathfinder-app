from __future__ import annotations

from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.tally_facts import TallyFact, TallyRowFact
from pathfinder.domain.turn_facts import StepFact, TurnFacts

_ID = "tally_cbc51c8c"
_FACTS = TurnFacts(
    record_noun="protein",
    steps=[
        StepFact(
            step_id="227288450",
            display_name="Number of Sequences",
            count=523795,
            reason=(
                "Singleton orthologous groups are defined by exactly one protein "
                "in the group."
            ),
            record_noun="group",
        )
    ],
    tallies=[
        TallyFact(
            id=_ID,
            title="Proteins by Taxon Code",
            record_noun="protein",
            total=2744,
            distinct=50,
            rows=[TallyRowFact(value="pyxn", count=898)],
        )
    ],
)


def test_a_count_noun_the_steps_qualify_after_a_tally_is_refused() -> None:
    prose = (
        f"The tally covers [tally:{_ID}:values] Plasmodium taxa and [tally:{_ID}] "
        "singleton protein records overall."
    )

    assert prose_faults(prose, _FACTS) == [
        ProseFault(
            token=f"[tally:{_ID}] singleton protein",
            kind="noun_after_count",
            references=(f"[tally:{_ID}]",),
        )
    ]


def test_a_tally_with_no_noun_after_it_stands() -> None:
    prose = (
        f"The tally covers [tally:{_ID}:values] Plasmodium taxa and [tally:{_ID}] "
        "overall."
    )

    assert prose_faults(prose, _FACTS) == []
