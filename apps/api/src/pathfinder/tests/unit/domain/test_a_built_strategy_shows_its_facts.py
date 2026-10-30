import json
from pathlib import Path

from pathfinder.domain.reply_note import note_facts
from pathfinder.domain.turn_facts import TurnFacts

_RECORDED = json.loads(
    (
        Path(__file__).parents[2] / "fixtures/turns/qa_built_strategy_facts.json"
    ).read_text()
)["turns"]


def _facts(name: str) -> TurnFacts:
    turn = _RECORDED[name]
    return TurnFacts.model_validate(
        {**turn["facts"], "requestMessages": [turn["message"]]}
    )


def test_the_signal_peptide_facts_show_the_count_the_reading_and_the_link() -> None:
    lines = _facts("signal_peptide").lines()

    assert lines[0] == "Predicted Signal Peptide: 479 genes"
    assert {
        "Organism: Plasmodium falciparum 3D7",
        "Version: SignalP-6.0",
        "Result: 479 genes",
        "https://qa.plasmodb.org/plasmo.qa/app/workspace/strategies/214647520/227288660",
    } <= set(lines)


def test_the_recorded_signal_peptide_reply_writes_the_count_and_the_link() -> None:
    turn = _RECORDED["signal_peptide"]

    assert note_facts(turn["reply"], _facts("signal_peptide")) == [
        "https://qa.plasmodb.org/plasmo.qa/app/workspace/strategies/214647520/227288660",
        "479",
    ]


def test_a_note_names_the_strain_and_the_version_as_they_stand() -> None:
    note = (
        "It reads the site's signal-peptide prediction for Plasmodium falciparum 3D7 "
        "with SignalP-6.0, the site's default version."
    )

    assert note_facts(note, _facts("signal_peptide")) == []


def test_the_orthogroup_facts_count_groups_once() -> None:
    lines = _facts("more_in_toxoplasma").lines()

    assert (
        lines[0],
        next(line for line in lines if line.startswith("Result:")),
    ) == ("Phyletic Pattern: 3,896 groups", "Result: 3,896 groups")


def test_the_recorded_orthogroup_reply_wrote_the_count_twice() -> None:
    turn = _RECORDED["more_in_toxoplasma"]

    assert note_facts(turn["reply"], _facts("more_in_toxoplasma")) == [
        "https://qa.orthomcl.org/orthomcl.qa/app/workspace/strategies/214647500/227288630",
        "3,896",
    ]
