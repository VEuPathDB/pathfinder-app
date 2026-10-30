"""A record the conversation showed last stays citable in a later turn: a record
reference links it, the facts part draws no row for it, and a record never shown
is dropped."""

from __future__ import annotations

from pathfinder.domain.record_facts import ListedFact, SourceFact
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.reply_note import linked_records, note_facts, render_note
from pathfinder.domain.turn_facts import TurnFacts

_HOSTDB_PAGE = "https://qa.hostdb.org/hostdb.qa/app/record/gene/"
_CRYPTO_PAGE = "https://qa.cryptodb.org/cryptodb.qa/app/record/gene/"
# hostdb, build 71: the sample of five a turn listed from the MHC class I
# intersect of chromosome 17 genes.
_SAMPLE = [
    "ENSMUSG00000035929",
    "ENSMUSG00000060550",
    "ENSMUSG00000061232",
    "ENSMUSG00000067212",
    "ENSMUSG00000067235",
]
_MUCIN = SourceFact(
    url=f"{_CRYPTO_PAGE}CPATCC_0009860",
    record_id="CPATCC_0009860",
    product="Cryptopsoridial mucin",
)


def _listed(record_id: str) -> SourceFact:
    return SourceFact(url=f"{_HOSTDB_PAGE}{record_id}", record_id=record_id)


_SHOWN = TurnFacts(shown_before=[*(_listed(g) for g in _SAMPLE), _MUCIN])


def test_a_listed_record_shown_before_renders_linked_to_its_page() -> None:
    prose = (
        "The sample was [record:ENSMUSG00000035929] and [record:ENSMUSG00000067235]."
    )

    assert render_note(prose, _SHOWN) == (
        f"The sample was [ENSMUSG00000035929]({_HOSTDB_PAGE}ENSMUSG00000035929) "
        f"and [ENSMUSG00000067235]({_HOSTDB_PAGE}ENSMUSG00000067235)\\."
    )


def test_a_read_record_shown_before_renders_linked_to_its_page() -> None:
    assert render_note("It is [record:CPATCC_0009860].", _SHOWN) == (
        f"It is [CPATCC_0009860]({_CRYPTO_PAGE}CPATCC_0009860)\\."
    )


def test_a_record_never_shown_is_dropped() -> None:
    assert render_note("It is [record:ENSMUSG00000073409].", _SHOWN) == "It is\\."


def test_records_shown_before_alone_are_no_site_data_of_this_turn() -> None:
    assert note_facts("The first is one of 5 genes.", _SHOWN) == []


def test_the_records_shown_before_are_no_row_and_no_record_of_this_turn() -> None:
    assert (
        _SHOWN.lines(),
        _SHOWN.empty(),
        _SHOWN.record_ids(),
        _SHOWN.shown_records(),
    ) == ([], True, [], [])


def test_the_records_shown_before_stay_off_the_wire() -> None:
    wire = _SHOWN.model_dump(by_alias=True, mode="json")

    assert ("shownBefore" in wire, TurnFacts.model_validate(wire).shown_before) == (
        False,
        [],
    )


def test_the_records_shown_before_are_redacted() -> None:
    redacted = _SHOWN.redacted(lambda text: text.replace("mucin", "[name]"))

    assert redacted.shown_before[-1].product == "Cryptopsoridial [name]"


def test_this_turn_shows_its_listed_then_its_read_records_once_each() -> None:
    ids = ["CPATCC_0031660", "CPATCC_0009860"]
    listed = [ListedRecord(record_id=g, url=f"{_CRYPTO_PAGE}{g}") for g in ids]
    facts = TurnFacts(
        listed=[ListedFact(step_id="step_text", records=listed)],
        sources=[_MUCIN, SourceFact(url="https://x/reference")],
    )

    assert (facts.shown_records(), facts.record_ids()) == (
        [SourceFact(url=f"{_CRYPTO_PAGE}CPATCC_0031660", record_id=ids[0]), _MUCIN],
        ids,
    )


def test_a_rendered_note_links_each_record_it_cites_once() -> None:
    prose = (
        "The sample was [record:ENSMUSG00000035929], [record:CPATCC_0009860] and "
        "[record:ENSMUSG00000035929] again."
    )

    assert linked_records(render_note(prose, _SHOWN)) == [
        "ENSMUSG00000035929",
        "CPATCC_0009860",
    ]
