"""The facts show each source under the step it was read from, with the fit
the check found, and each count an edit moved beside the count it held before."""

from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.turn_facts import (
    ListedFact,
    SourceFact,
    StepFact,
    TurnFacts,
)

_TOXO = "https://qa.toxodb.org/toxo.qa/app/record/gene"


def _leaf_and_root() -> TurnFacts:
    """A leaf of 627 genes under a root of 9, and one record read from the leaf."""
    return TurnFacts(
        steps=[
            StepFact(step_id="step_d2536be6", display_name="SignalP", count=627),
            StepFact(
                step_id="step_root",
                display_name="Orthology",
                operator="MINUS",
                count=9,
            ),
        ],
        root_count=9,
        sources=[
            SourceFact(
                url=f"{_TOXO}/TGME49_200010",
                record_id="TGME49_200010",
                product="hypothetical protein",
                step_id="step_d2536be6",
                step_name="SignalP",
                fit="unclear",
            ),
            SourceFact(url="https://doi.org/10.1016/j.cell.2008.01.001"),
        ],
    )


def test_a_leaf_s_record_is_shown_under_the_leaf_not_the_result() -> None:
    assert _leaf_and_root().lines() == [
        "SignalP: 627 genes",
        (
            "Read from SignalP: TGME49_200010, hypothetical protein (the check "
            f"judged its fit unclear): {_TOXO}/TGME49_200010"
        ),
        "MINUS Orthology: 9 genes",
        "Result: 9 genes",
        "Read: https://doi.org/10.1016/j.cell.2008.01.001",
    ]


def test_a_record_of_a_step_the_strategy_no_longer_holds_is_not_shown() -> None:
    gone = SourceFact(
        url=f"{_TOXO}/TGME49_1",
        record_id="TGME49_1",
        step_id="step_gone",
        step_name="InterPro",
        fit="yes",
    )
    read = SourceFact(url=f"{_TOXO}/TGME49_2", record_id="TGME49_2")

    assert TurnFacts(sources=[gone, read]).lines() == [
        f"Read: TGME49_2: {_TOXO}/TGME49_2"
    ]


def test_an_edited_step_and_the_result_show_the_count_before_the_edit() -> None:
    facts = TurnFacts(
        steps=[
            StepFact(
                step_id="c_org",
                display_name="Text search",
                count=19,
                count_before=2160,
            )
        ],
        root_count=19,
        root_count_before=2160,
    )

    assert facts.lines() == [
        "Text search: 19 genes, 2,160 genes before this turn's edit",
        "Result: 19 genes, 2,160 genes before this turn's edit",
    ]


def test_the_genes_the_message_names_are_listed_with_their_records() -> None:
    named = SourceFact(
        url="https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_0709000",
        record_id="PF3D7_0709000",
        product="chloroquine resistance transporter",
        organism="Plasmodium falciparum 3D7",
    )
    facts = TurnFacts(named_genes=[named])

    assert (facts.empty(), facts.lines()) == (
        False,
        [
            (
                "Named in the message: PF3D7_0709000, chloroquine resistance "
                "transporter, Plasmodium falciparum 3D7: "
                "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_0709000"
            )
        ],
    )


def test_the_ids_a_listing_returned_are_shown_under_their_step() -> None:
    facts = TurnFacts(
        steps=[StepFact(step_id="step_hha", display_name="Text search", count=23)],
        listed=[
            ListedFact(
                step_id="step_hha",
                step_name="Text search",
                records=[
                    ListedRecord(record_id=g, url=f"https://qa.toxodb.org/{g}")
                    for g in ("HHA_208730", "HHA_208740")
                ],
            )
        ],
    )

    assert facts.lines() == [
        "Text search: 23 genes",
        "Listed from Text search: HHA_208730, HHA_208740",
    ]


def test_a_record_is_shown_with_its_words_and_its_link() -> None:
    read = SourceFact(
        url="https://qa.tritrypdb.org/tritrypdb.qa/app/record/gene/Tbg972.6.590",
        record_id="Tbg972.6.590",
        product="hypothetical protein",
        organism="T. brucei gambiense DAL972",
        values=["chromosome 6"],
    )
    facts = TurnFacts(sources=[read])

    assert facts.lines() == [
        (
            "Read: Tbg972.6.590, hypothetical protein, T. brucei gambiense DAL972, "
            "chromosome 6: https://qa.tritrypdb.org/tritrypdb.qa/app/record/gene/"
            "Tbg972.6.590"
        )
    ]
