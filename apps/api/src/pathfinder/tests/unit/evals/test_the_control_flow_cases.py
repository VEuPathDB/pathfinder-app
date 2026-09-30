"""The round-3 cases on the turn's control flow hold what the fixes promise."""

from __future__ import annotations

from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_polar_tube_conversation_ends_on_an_answer() -> None:
    case = _BY_NAME["uat-dry3-d-microsporidiadb"]
    expected = case.expected

    assert len(case.turns) == 5
    assert "Send the message again" in expected.turn_reply_omits[4]
    assert (expected.structure, expected.step_count) == ("GenesByText", 1)
    assert expected.root_count is not None
    assert expected.root_count.count == 1


def test_the_strain_comparison_leaves_the_root_at_its_count() -> None:
    case = _BY_NAME["uat-dry3-b-tritrypdb"]
    expected = case.expected

    assert (expected.structure, expected.step_count, expected.root_operator) == (
        "GenesByInterproDomain",
        1,
        None,
    )
    assert expected.root_count is not None
    assert expected.root_count.count == 37
    assert "80 genes" in expected.turn_reply_omits[1]


def test_the_glycosome_sample_is_listed_after_one_read_each() -> None:
    case = _BY_NAME["uat-dry3-d-veupathdb"]
    expected = case.expected

    assert expected.turn_reply_mentions[3] == [
        "LdBPK_010310.1",
        "LdBPK_030050.1",
        "LdBPK_040440.1",
        "LdBPK_041170.1",
        "LdBPK_050090.1",
    ]
    assert expected.root_count is not None
    assert expected.root_count.count == 115
