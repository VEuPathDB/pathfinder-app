"""A synthetic OrthoMCL taxonomy: one clade per entry, each holding that many genomes."""

from __future__ import annotations

import string
from itertools import product

from veupathdb.domain.parameters import PhyleticTree, TaxonEntry

_PAIRS = ["".join(pair) for pair in product(string.ascii_lowercase, repeat=2)]


def clade_codes(clade: str, size: int) -> list[str]:
    return [f"{clade[:2].lower()}{pair}" for pair in _PAIRS[:size]]


def clade_tree(clades: dict[str, int]) -> PhyleticTree:
    entries = [
        TaxonEntry(id="ALL", parent_id=None, code="ALL", label="All", clade=True)
    ]
    for clade, size in clades.items():
        entries.append(
            TaxonEntry(id=clade, parent_id="ALL", code=clade, label=clade, clade=True)
        )
        entries.extend(
            TaxonEntry(id=code, parent_id=clade, code=code, label=code, clade=False)
            for code in clade_codes(clade, size)
        )
    return PhyleticTree.from_taxa(entries)
