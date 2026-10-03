"""The cases on the phrase reading and the stated labels expect the word and
phrase counts and the stated organism the facts show."""

from __future__ import annotations

from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_cysteine_case_shows_the_word_and_phrase_counts_and_the_organism_stated() -> (
    None
):
    case = _BY_NAME["uat-core-b-giardiadb"]
    expected = case.expected

    assert len(case.turns) == 3
    assert expected.turn_reply_mentions == {0: ["Roberts-Thomson (stated)"]}
    assert expected.parameters["GenesByText"] == {
        "text_search_organism": "Giardia muris strain Roberts-Thomson"
    }
    assert case.gates.policy == "leave"
    assert expected.structure == "(GenesByText MINUS GenesByTransmembraneDomains)"


def test_the_zinc_finger_case_shows_the_organism_stated() -> None:
    """The sample a pass picks is its own, so the case pins only the organism."""
    case = _BY_NAME["uat-dry4-b-tritrypdb"]
    expected = case.expected

    assert expected.turn_reply_mentions == {0: ["Leishmania infantum JPCM5 (stated)"]}
    assert expected.turn_reply_omits == {1: ["site's default 0"]}
    assert case.assert_de_identified()
