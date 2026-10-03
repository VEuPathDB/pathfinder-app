"""The cases on the turn's control flow hold what the turn promises."""

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
    # An open family lookup binds a different entry set on each pass, so the
    # case pins the structure and the organism, never the count.
    assert [expected.root_count] == [None]
    assert "80 genes" in expected.turn_reply_omits[1]


def test_the_glycosome_sample_is_listed_after_one_read_each() -> None:
    case = _BY_NAME["uat-dry3-d-veupathdb"]
    expected = case.expected

    # The sample's ids depend on the step the run creates, so the case pins
    # no id; the same-sample rule is the runner's to score.
    assert expected.turn_reply_mentions == {}
    assert expected.root_count is not None
    assert expected.root_count.count == 115


def test_the_organism_edit_lands_on_both_searches_and_keeps_their_values() -> None:
    """The edit re-binds the organism it names and keeps the union's values."""
    case = _BY_NAME["edit-keeps-the-criteria-it-was-told-to-keep"]
    expected = case.expected

    assert case.turns[1] == (
        "Swap the organism on both searches to Plasmodium vivax P01 and keep "
        "everything else as it is."
    )
    assert (expected.structure, expected.step_count, expected.root_count) == (
        "(GenesByText UNION GenesByGoTerm)",
        3,
        None,
    )
    assert expected.parameters == {
        "GenesByText": {"text_search_organism": "Plasmodium vivax P01"},
        "GenesByGoTerm": {
            "organism": "Plasmodium vivax P01",
            "go_typeahead": "GO:0016301",
        },
    }
