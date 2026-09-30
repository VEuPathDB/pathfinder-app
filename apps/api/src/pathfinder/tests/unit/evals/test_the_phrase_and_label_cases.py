"""The round-4 cases on the phrase reading and the stated labels hold what the
fixes promise."""

from __future__ import annotations

from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_cysteine_case_shows_the_exact_phrase_at_zero_and_the_organism_stated() -> (
    None
):
    case = _BY_NAME["uat-dry4-b-giardiadb"]
    expected = case.expected

    assert len(case.turns) == 3
    assert expected.turn_reply_mentions == {
        0: [
            "Roberts-Thomson) (stated)",
            'as the phrase "cysteine-rich protein": 0 genes',
        ],
        2: ['as the phrase "cysteine-rich protein": 0 genes'],
    }
    assert expected.structure == "(GenesByText MINUS GenesByTransmembraneDomains)"


def test_the_zinc_finger_case_shows_the_organism_stated_and_the_sample_chosen() -> None:
    case = _BY_NAME["uat-dry4-b-tritrypdb"]
    expected = case.expected

    assert expected.turn_reply_mentions == {
        0: ["Leishmania infantum JPCM5) (stated)"],
        1: ["Samples: 0 hr (0 hr) (chosen)"],
    }
    assert expected.turn_reply_omits == {1: ["site's default 0"]}
    assert case.assert_de_identified()
