"""The conversation keeps its last exchanges as the researcher read them, oldest
first, and renders them for the Lead with what each one said and showed."""

from __future__ import annotations

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.domain.exchanges import EXCHANGE_WINDOW, Exchange, exchanges_section

_SAMPLE = (
    "Here is a sample of five genes: ENSMUSG00000035929, ENSMUSG00000060550, "
    "ENSMUSG00000061232, ENSMUSG00000067212 and ENSMUSG00000067235."
)


def test_no_exchange_renders_no_section() -> None:
    assert [exchanges_section([])] == [None]


def test_each_kind_of_exchange_renders_what_it_said_and_showed() -> None:
    exchanges = [
        Exchange(
            said="Put it back to chromosome 17 and show me five genes.", reply=_SAMPLE
        ),
        Exchange(
            said="Keep SRP171130 then.",
            reply="Which male-antennae samples should I exclude?",
            card="Exclude male antennae samples (options: all male antennae; none)",
        ),
        Exchange(kind="card_answer", said="all male antennae", reply="Done: 12 genes."),
        Exchange(kind="task_result", reply="The control test finished: 4 of 5 found."),
    ]

    assert exchanges_section(exchanges) == "\n".join(
        [
            "## The conversation so far",
            (
                "The last exchanges of this conversation, oldest first, as the "
                "researcher read them. A number or a record in them held when it "
                "was shown; the ledger and the facts hold the strategy now."
            ),
            "",
            "Researcher: Put it back to chromosome 17 and show me five genes.",
            f"You replied: {_SAMPLE}",
            "",
            "Researcher: Keep SRP171130 then.",
            "You replied: Which male-antennae samples should I exclude?",
            (
                "You asked on a card: Exclude male antennae samples (options: all "
                "male antennae; none)"
            ),
            "",
            "Researcher answered the card: all male antennae",
            "You replied: Done: 12 genes.",
            "",
            "A background task finished.",
            "You replied: The control test finished: 4 of 5 found.",
        ]
    )


def test_the_conversation_keeps_its_last_exchanges_in_order() -> None:
    domain = StrategyDomainState()

    for n in range(EXCHANGE_WINDOW + 2):
        domain.record_exchange(Exchange(said=f"message {n}", reply=f"reply {n}"))

    assert [e.said for e in domain.exchanges] == [
        f"message {n}" for n in range(2, EXCHANGE_WINDOW + 2)
    ]


def test_an_exchange_that_said_and_showed_nothing_is_not_kept() -> None:
    domain = StrategyDomainState()

    domain.record_exchange(Exchange())

    assert domain.exchanges == []
