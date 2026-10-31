import json
from pathlib import Path

from pathfinder.domain.turn_facts import TurnFacts

_RECORDED = json.loads(
    (
        Path(__file__).parents[2] / "fixtures/turns/qa_built_strategy_facts.json"
    ).read_text()
)["turns"]


def _facts(name: str) -> TurnFacts:
    turn = _RECORDED[name]
    return TurnFacts.model_validate(turn["facts"])


def test_the_signal_peptide_facts_show_the_count_the_reading_and_the_link() -> None:
    lines = _facts("signal_peptide").lines()

    assert lines[0] == "Predicted Signal Peptide: 479 genes"
    assert {
        "Organism: Plasmodium falciparum 3D7",
        "Version: SignalP-6.0",
        "Result: 479 genes",
        "https://qa.plasmodb.org/plasmo.qa/app/workspace/strategies/214647520/227288660",
    } <= set(lines)


def test_the_orthogroup_facts_count_groups_once() -> None:
    lines = _facts("more_in_toxoplasma").lines()

    assert (
        lines[0],
        next(line for line in lines if line.startswith("Result:")),
    ) == ("Phyletic Pattern: 3,896 groups", "Result: 3,896 groups")
