"""The round-3 cases on a requirement's lifecycle hold what the fixes promise."""

from __future__ import annotations

from pathfinder.evals.case import GatePlan
from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_polar_tube_comparison_records_no_side_as_a_requirement() -> None:
    case = _BY_NAME["uat-dry3-d-sides-microsporidiadb"]
    expected = case.expected

    assert len(case.turns) == 2
    assert (expected.structure, expected.step_count) == ("GenesByText", 1)
    assert expected.turn_reply_omits[1] == [
        "'polar tube protein family'",
        "'InterPro OR Pfam'",
    ]
    assert expected.root_count is not None
    assert expected.root_count.count == 1


def test_the_widen_card_offers_nothing_that_cannot_move_the_count() -> None:
    case = _BY_NAME["uat-dry3-a-cryptodb"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (2, GatePlan(policy="auto"))
    assert (expected.structure, expected.step_count, expected.assumed_stated) == (
        "GenesWithSignalPeptide",
        1,
        0,
    )
    assert "Protein Coding Only: all" in expected.turn_reply_omits[0]
    assert "'0' is withdrawn" in expected.turn_reply_omits[1]
    assert expected.root_count is not None
    assert expected.root_count.count == 421


def test_the_winnie_case_names_no_card_label_as_a_gap() -> None:
    expected = _BY_NAME["uat-dry-c-piroplasmadb"].expected

    assert expected.turn_reply_omits == {0: ["'Specify an alternative evidence type'"]}
