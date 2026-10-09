"""A turn's answer is the records its reply links; the ids a check listed beside
that reply are evidence. A reply that links none answers with the ids listed."""

from __future__ import annotations

from pathfinder.devtools.eval_runner import records_shown
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.turn_facts import ListedFact, TurnFacts

# hostdb: a check sampled eight of the nine genes, the reply linked five.
_SAMPLED = [
    "ENSMUSG00000073409",
    "ENSMUSG00000073411",
    "ENSMUSG00000079507",
    "ENSMUSG00000035929",
    "ENSMUSG00000060550",
    "ENSMUSG00000061232",
    "ENSMUSG00000067212",
    "ENSMUSG00000067235",
]
_LINKED = _SAMPLED[3:]


def _page(record_id: str) -> str:
    return f"https://qa.hostdb.org/hostdb.qa/app/record/gene/{record_id}"


def _listing(ids: list[str]) -> TurnFacts:
    return TurnFacts(
        listed=[
            ListedFact(
                step_id="step_root",
                step_name="Intersect",
                records=[ListedRecord(record_id=i, url=_page(i)) for i in ids],
            )
        ]
    )


def test_the_records_a_reply_links_are_the_answer() -> None:
    reply = "The sample: " + ", ".join(f"[{i}]({_page(i)})" for i in _LINKED)

    assert [
        records_shown(_listing(_SAMPLED), reply),
        records_shown(_listing(_SAMPLED[:3]), "The ids are listed beside this reply."),
    ] == [_LINKED, _SAMPLED[:3]]
