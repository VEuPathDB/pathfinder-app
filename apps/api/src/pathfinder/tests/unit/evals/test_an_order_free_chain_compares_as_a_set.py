from __future__ import annotations

from pathfinder.evals.scoring import canonical_structure


def test_a_reordered_intersect_chain_compares_equal() -> None:
    built = "((GenesByExportPrediction INTERSECT GenesByTransmembraneDomains) INTERSECT GenesWithSignalPeptide)"
    expected = "((GenesByTransmembraneDomains INTERSECT GenesWithSignalPeptide) INTERSECT GenesByExportPrediction)"

    assert canonical_structure(built) == canonical_structure(expected)


def test_a_chain_of_two_operators_keeps_its_grouping() -> None:
    first = "((A INTERSECT B) UNION C)"
    second = "((A UNION C) INTERSECT B)"

    assert canonical_structure(first) != canonical_structure(second)


def test_a_minus_keeps_its_order() -> None:
    assert canonical_structure("(A MINUS B)") != canonical_structure("(B MINUS A)")
