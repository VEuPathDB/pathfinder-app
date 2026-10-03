"""The term a vocabulary label names is the label without the value it leads
with and without a trailing depth."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.value_label import label_term


@pytest.mark.parametrize(
    ("value", "display", "term"),
    [
        ("GO:0006955", "GO:0006955 : immune response : 3", "immune response"),
        ("PF00069", "PF00069 : Pkinase", "Pkinase"),
        ("PF00069", "PF00069 : Protein kinase domain", "Protein kinase domain"),
        ("pfal3D7", "Plasmodium falciparum 3D7", "Plasmodium falciparum 3D7"),
        ("3", "Chromosome 3 : 12", "Chromosome 3"),
    ],
)
def test_the_term_of_a_label(value: str, display: str, term: str) -> None:
    assert label_term(value, display) == term
