"""A column tally is a fact: a reply states each count and the total with a
``tally`` reference, and a bare count is a fault that names the reference."""

from __future__ import annotations

from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.domain.tally_facts import TallyFact, TallyRowFact, tally_id
from pathfinder.domain.turn_facts import TurnFacts

_ID = tally_id(
    "vectorbase", "AllDatasets", "organism_prefix", ("newcategory", ("RNASeq",))
)

_TALLY = TallyFact(
    id=_ID,
    title="Datasets by Organism(s), where Category is RNASeq",
    record_noun="dataset",
    total=379,
    distinct=58,
    rows=[
        TallyRowFact(value="Anopheles gambiae PEST", count=40),
        TallyRowFact(value="Anopheles coluzzii AcolN3", count=11),
    ],
)


def test_a_tally_reference_renders_a_count_in_the_tallys_own_noun() -> None:
    facts = TurnFacts(tallies=[_TALLY])

    assert render_reply(
        f"PEST has [tally:{_ID}.Anopheles gambiae PEST] of [tally:{_ID}] in all.",
        facts,
    ) == ("PEST has 40 datasets of 379 datasets in all.")


def test_the_noun_written_after_a_tally_reference_is_absorbed() -> None:
    facts = TurnFacts(tallies=[_TALLY])

    assert (
        render_reply(
            f"AcolN3 has [tally:{_ID}.Anopheles coluzzii AcolN3] datasets.", facts
        )
        == "AcolN3 has 11 datasets."
    )


def test_a_bare_count_names_the_tally_reference_that_renders_it() -> None:
    facts = TurnFacts(tallies=[_TALLY])

    faults = prose_faults("PEST has 40 RNA-Seq datasets.", facts)

    assert [(f.token, f.references) for f in faults] == [
        ("40", (f"[tally:{_ID}.Anopheles gambiae PEST]",))
    ]


def test_a_tally_id_is_the_same_on_every_read_and_differs_by_filter() -> None:
    again = tally_id(
        "vectorbase", "AllDatasets", "organism_prefix", ("newcategory", ("RNASeq",))
    )
    unfiltered = tally_id("vectorbase", "AllDatasets", "organism_prefix", None)

    assert again == _ID
    assert unfiltered != _ID
    assert _ID.startswith("tally_")


def test_a_tally_shows_its_title_its_total_and_each_count() -> None:
    assert _TALLY.lines() == [
        "Datasets by Organism(s), where Category is RNASeq",
        f"[tally:{_ID}] = 379 datasets",
        f"[tally:{_ID}:values] = 58 values",
        f"[tally:{_ID}.Anopheles gambiae PEST] = 40",
        f"[tally:{_ID}.Anopheles coluzzii AcolN3] = 11",
    ]


def test_a_tally_values_reference_renders_how_many_values_it_counted() -> None:
    facts = TurnFacts(tallies=[_TALLY])

    assert render_reply(
        f"It has [tally:{_ID}] across [tally:{_ID}:values].", facts
    ) == ("It has 379 datasets across 58 values.")
    assert render_reply(f"Across [tally:{_ID}:values] values.", facts) == (
        "Across 58 values."
    )


def test_a_bare_count_of_values_names_the_values_reference() -> None:
    facts = TurnFacts(tallies=[_TALLY])

    faults = prose_faults("They span 58 organisms.", facts)

    assert [(f.token, f.references) for f in faults] == [
        ("58", (f"[tally:{_ID}:values]",))
    ]
