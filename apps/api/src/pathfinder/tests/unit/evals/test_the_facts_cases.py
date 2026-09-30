"""The round-3 cases on what a turn shows hold what the fixes promise."""

from __future__ import annotations

from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_orthology_join_shows_no_count_before_a_step_it_created() -> None:
    expected = _BY_NAME["uat-dry3-a-toxodb"].expected

    assert "6,123 genes before this turn's edit" in expected.turn_reply_omits[1]
    assert "Listed from" in expected.turn_reply_mentions[2]
    assert expected.root_count is not None
    assert expected.root_count.count == 19


def test_the_volcano_export_names_its_filters_and_counts_its_cut() -> None:
    expected = _BY_NAME["uat-dry3-b-fungidb"].expected

    assert expected.turn_reply_mentions[0] == [
        "genotype is one of wild type",
        "fraction is one of total",
        "of 7,884 genes tested",
    ]
    assert "VAR_84f17484" in expected.turn_reply_omits[0]
    assert (expected.structure, expected.step_count) == ("GenesByEdaVizWithCompute", 1)


def test_the_location_case_shows_the_placeholder_as_not_set() -> None:
    case = _BY_NAME["uat-dry3-d-hostdb"]
    expected = case.expected

    assert len(case.turns) == 4
    assert expected.turn_reply_mentions[0] == ["not set (site placeholder)"]
    assert expected.root_count is not None
    assert expected.root_count.count == 9
